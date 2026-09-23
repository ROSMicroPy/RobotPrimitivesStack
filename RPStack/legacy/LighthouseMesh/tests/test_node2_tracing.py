import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
OTEL_ROOT = ROOT.parent / "MicropythonModules" / "mp_opentelemetry" / "src"
DNET_ROOT = ROOT / "dnet" / "src"
NODE2_DEMO_PATH = ROOT / "node2" / "demo.py"


def _load_package(name, init_path, package_root):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name,
        str(init_path),
        submodule_search_locations=[str(package_root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_module(name, module_path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(module_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _ensure_namespace_package(name, package_root):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(package_root)]
        sys.modules[name] = module
    return module


class _FakeWLAN:
    def active(self, *args, **kwargs):
        return True

    def isconnected(self):
        return True

    def config(self, key=None):
        if key == "channel":
            return 6
        return None

    def ifconfig(self):
        return ("192.168.1.22", "255.255.255.0", "192.168.1.1", "8.8.8.8")

    def connect(self, *args, **kwargs):
        return None


class _FakeTransport:
    def __init__(self, incoming=None):
        self.incoming = list(incoming or [])
        self.sent = []

    def send(self, peer_id, payload, message=None):
        self.sent.append({"peer_id": peer_id, "payload": payload, "message": message})

    def recv(self):
        if not self.incoming:
            return None, None
        return self.incoming.pop(0)


class Node2TracingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _load_package("otel", OTEL_ROOT / "__init__.py", OTEL_ROOT)
        _ensure_namespace_package("dnet", DNET_ROOT)
        _ensure_namespace_package("dnet.signalling", DNET_ROOT / "signalling")

        network_module = types.ModuleType("network")
        network_module.STA_IF = 0
        network_module.WLAN = lambda *_args, **_kwargs: _FakeWLAN()
        sys.modules["network"] = network_module

        ntptime_module = types.ModuleType("ntptime")
        ntptime_module.settime = lambda: None
        sys.modules["ntptime"] = ntptime_module

        mesh_module = types.ModuleType("dnet.signalling.LighthouseMesh")
        mesh_module.LighthouseMesh = object
        sys.modules["dnet.signalling.LighthouseMesh"] = mesh_module

        from otel.api import set_logger_provider, set_tracer_provider
        from otel.logging import LoggerProvider
        from otel.trace import TracerProvider

        set_tracer_provider(TracerProvider(resource={"service.name": "trace-test"}))
        set_logger_provider(LoggerProvider(resource={"service.name": "trace-test"}))

        cls.node2_demo = _load_module("node2_demo_for_tests", NODE2_DEMO_PATH)

    def test_node1_trace_id_is_reused_by_node2_ack(self):
        from dnet.messaging import MessagingEndpoint, Schema
        from otel.api import get_tracer_provider

        sender_transport = _FakeTransport()
        sender_endpoint = MessagingEndpoint(node_id="node1", transport=sender_transport)

        sent_payload = sender_endpoint.send_event(
            peer_id="node2",
            event_name="sensor.distance.measured",
            parameters={"distance_mm": 321},
            ttl_ms=2500,
        )
        sent_message = sender_endpoint.codec.decode(sent_payload)

        receiver_transport = _FakeTransport(incoming=[("node1", sent_payload)])
        receiver_endpoint = MessagingEndpoint(node_id="node2", transport=receiver_transport)

        self.node2_demo.ACK_ENDPOINT = receiver_endpoint
        self.node2_demo.NODE_IDENTITY.clear()
        self.node2_demo.NODE_IDENTITY["node_id"] = "node2"

        peer_id, message = receiver_endpoint.poll()
        with receiver_endpoint.message_context(peer_id, message):
            self.node2_demo.on_message(peer_id, message)

        self.assertEqual(1, len(receiver_transport.sent))
        ack_payload = receiver_transport.sent[0]["payload"]
        ack_message = receiver_endpoint.codec.decode(ack_payload)

        sent_trace = sent_message[Schema.F_TRACE]
        ack_trace = ack_message[Schema.F_TRACE]

        self.assertEqual(Schema.TYPE_REPORT, ack_message[Schema.F_TYPE])
        self.assertEqual(sent_trace["trace_id"], ack_trace["trace_id"])
        self.assertNotEqual(sent_trace["span_id"], ack_trace["span_id"])

        spans = get_tracer_provider().snapshot()
        by_name = {}
        for span in spans:
            by_name.setdefault(span["name"], []).append(span)

        receive_span = by_name["dnet.messaging.receive"][-1]
        app_span = by_name["node2.on_message"][-1]
        ack_app_span = by_name["node2.send_event_ack"][-1]
        ack_span = by_name["dnet.messaging.send.report"][-1]

        self.assertEqual(sent_trace["trace_id"], receive_span["trace_id"])
        self.assertEqual(sent_trace["trace_id"], app_span["trace_id"])
        self.assertEqual(sent_trace["trace_id"], ack_app_span["trace_id"])
        self.assertEqual(sent_trace["trace_id"], ack_span["trace_id"])
        self.assertEqual(receive_span["span_id"], app_span["parent_span_id"])
        self.assertEqual(app_span["span_id"], ack_app_span["parent_span_id"])
        self.assertEqual(ack_app_span["span_id"], ack_span["parent_span_id"])

    def test_resolve_mesh_channel_prefers_connected_wifi_channel(self):
        class ChannelOneWLAN(_FakeWLAN):
            def config(self, key=None):
                if key == "channel":
                    return 1
                return None

        channel = self.node2_demo._resolve_mesh_channel({"mesh_channel": 6}, ChannelOneWLAN())
        self.assertEqual(1, channel)


if __name__ == "__main__":
    unittest.main()
