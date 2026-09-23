import importlib.util
import json
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
OTEL_ROOT = ROOT.parent / "MicropythonModules" / "mp_opentelemetry" / "src"
DNET_ROOT = ROOT / "dnet" / "src"


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


def _ensure_namespace_package(name, package_root):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(package_root)]
        sys.modules[name] = module
    return module


class _TracingFakeMesh:
    def __init__(self, tracer, codec):
        self.tracer = tracer
        self.codec = codec
        self.default_peer = "broadcast"
        self.sent = []
        self.incoming = []
        self._last_recv_trace_context = None
        self._last_recv_metadata = None

    def send_raw(self, peer, payload):
        payload_bytes = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        with self.tracer.start_span(
            "dnet.signalling.mesh.send_raw",
            attributes={"peer_id": str(peer), "transport": "espnow"},
            kind="internal",
        ) as span:
            span.set_attribute("message.bytes", len(payload_bytes))
            self.sent.append((peer, payload, span.context))

    def recv_raw(self, timeout_ms=0):
        if not self.incoming:
            return None, None
        mac, payload = self.incoming.pop(0)
        parent_context = self._extract_payload_context(payload)
        with self.tracer.start_span(
            "dnet.signalling.mesh.recv_raw",
            parent_context=parent_context,
            attributes={"peer_id": self.mac_to_node_id(mac), "transport": "espnow"},
            kind="internal",
        ) as span:
            payload_bytes = payload if isinstance(payload, bytes) else payload.encode("utf-8")
            span.set_attribute("message.bytes", len(payload_bytes))
            self._last_recv_trace_context = span.context
            self._last_recv_metadata = {"queued_ms": 0, "ingest_source": "test"}
        return mac, payload

    def mac_to_node_id(self, mac):
        if isinstance(mac, bytes):
            return mac.decode("utf-8")
        return str(mac)

    def consume_recv_trace_context(self):
        context = self._last_recv_trace_context
        self._last_recv_trace_context = None
        return context

    def consume_recv_metadata(self):
        metadata = self._last_recv_metadata
        self._last_recv_metadata = None
        return metadata

    def _extract_payload_context(self, payload):
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        try:
            message = json.loads(payload)
        except Exception:
            return None
        return self.codec.extract_trace_context(message)


class DNetTraceContinuityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _load_package("otel", OTEL_ROOT / "__init__.py", OTEL_ROOT)
        _ensure_namespace_package("dnet", DNET_ROOT)
        _ensure_namespace_package("dnet.signalling", DNET_ROOT / "signalling")

    def setUp(self):
        from otel.api import set_logger_provider, set_meter_provider, set_tracer_provider
        from otel.logging import LoggerProvider
        from otel.metric import MeterProvider
        from otel.trace import TracerProvider

        set_tracer_provider(TracerProvider(resource={"service.name": "dnet-trace-test"}))
        set_logger_provider(LoggerProvider(resource={"service.name": "dnet-trace-test"}))
        set_meter_provider(MeterProvider(resource={"service.name": "dnet-trace-test"}))

    def test_node1_span_flows_down_to_dnet_send_layers(self):
        from dnet.messaging import MessageCodec, MessagingEndpoint
        from dnet.signalling.LighthouseTransport import LighthouseMeshTransport
        from otel.api import get_tracer, get_tracer_provider

        codec = MessageCodec()
        mesh = _TracingFakeMesh(get_tracer("dnet.signalling.mesh"), codec)
        transport = LighthouseMeshTransport(mesh, default_peer="node2")
        endpoint = MessagingEndpoint(node_id="node1", transport=transport, codec=codec)

        with get_tracer("node1.demo").start_span("node1.send_distance_event", kind="internal"):
            endpoint.send_event(
                peer_id="node2",
                event_name="sensor.distance.measured",
                parameters={"distance_mm": 100},
                ttl_ms=2500,
            )

        spans = get_tracer_provider().snapshot()
        by_name = {span["name"]: span for span in spans}

        node_span = by_name["node1.send_distance_event"]
        messaging_span = by_name["dnet.messaging.send.event"]
        transport_span = by_name["dnet.signalling.transport.send"]
        mesh_span = by_name["dnet.signalling.mesh.send_raw"]

        self.assertEqual(node_span["trace_id"], messaging_span["trace_id"])
        self.assertEqual(node_span["trace_id"], transport_span["trace_id"])
        self.assertEqual(node_span["trace_id"], mesh_span["trace_id"])
        self.assertEqual(node_span["span_id"], messaging_span["parent_span_id"])
        self.assertEqual(messaging_span["span_id"], transport_span["parent_span_id"])
        self.assertEqual(transport_span["span_id"], mesh_span["parent_span_id"])

    def test_trace_is_contiguous_within_and_across_devices(self):
        from dnet.messaging import MessageCodec, MessagingEndpoint, Schema
        from dnet.signalling.LighthouseTransport import LighthouseMeshTransport
        from otel.api import get_tracer, get_tracer_provider

        codec = MessageCodec()

        sender_mesh = _TracingFakeMesh(get_tracer("dnet.signalling.mesh"), codec)
        sender_transport = LighthouseMeshTransport(sender_mesh, default_peer="node2")
        sender_endpoint = MessagingEndpoint(node_id="node1", transport=sender_transport, codec=codec)

        with get_tracer("node1.demo").start_span("node1.send_distance_event", kind="internal"):
            sent_payload = sender_endpoint.send_event(
                peer_id="node2",
                event_name="sensor.distance.measured",
                parameters={"distance_mm": 321},
                ttl_ms=None,
            )

        sent_message = codec.decode(sent_payload)

        receiver_mesh = _TracingFakeMesh(get_tracer("dnet.signalling.mesh"), codec)
        receiver_mesh.incoming.append(("node1", sent_payload))
        receiver_transport = LighthouseMeshTransport(receiver_mesh, default_peer="node1")
        receiver_endpoint = MessagingEndpoint(node_id="node2", transport=receiver_transport, codec=codec)

        peer_id, message = receiver_endpoint.poll()
        with receiver_endpoint.message_context(peer_id, message):
            with get_tracer("node2.demo").start_span("node2.on_message", kind="consumer"):
                receiver_endpoint.send_report(
                    peer_id=peer_id,
                    subject="sensor.distance.measured",
                    status="received",
                    detail={"source_sequence": message.get(Schema.F_SEQUENCE)},
                )

        ack_payload = receiver_mesh.sent[-1][1]
        ack_message = codec.decode(ack_payload)

        self.assertEqual(sent_message[Schema.F_TRACE]["trace_id"], ack_message[Schema.F_TRACE]["trace_id"])
        self.assertLessEqual(len(sent_payload), 245)

        spans = get_tracer_provider().snapshot()
        by_name = {}
        for span in spans:
            by_name.setdefault(span["name"], []).append(span)

        send_node_span = by_name["node1.send_distance_event"][-1]
        send_msg_span = by_name["dnet.messaging.send.event"][-1]
        send_transport_span = by_name["dnet.signalling.transport.send"][0]
        send_mesh_span = by_name["dnet.signalling.mesh.send_raw"][0]
        recv_mesh_span = by_name["dnet.signalling.mesh.recv_raw"][-1]
        recv_transport_span = by_name["dnet.signalling.transport.recv"][-1]
        poll_span = by_name["dnet.messaging.poll"][-1]
        receive_span = by_name["dnet.messaging.receive"][-1]
        node2_span = by_name["node2.on_message"][-1]
        ack_msg_span = by_name["dnet.messaging.send.report"][-1]
        ack_transport_span = by_name["dnet.signalling.transport.send"][-1]
        ack_mesh_span = by_name["dnet.signalling.mesh.send_raw"][-1]

        trace_id = sent_message[Schema.F_TRACE]["trace_id"]
        for span in (
            send_node_span,
            send_msg_span,
            send_transport_span,
            send_mesh_span,
            recv_mesh_span,
            recv_transport_span,
            poll_span,
            receive_span,
            node2_span,
            ack_msg_span,
            ack_transport_span,
            ack_mesh_span,
        ):
            self.assertEqual(trace_id, span["trace_id"])

        self.assertEqual(send_node_span["span_id"], send_msg_span["parent_span_id"])
        self.assertEqual(send_msg_span["span_id"], send_transport_span["parent_span_id"])
        self.assertEqual(send_transport_span["span_id"], send_mesh_span["parent_span_id"])
        self.assertEqual(send_msg_span["span_id"], recv_mesh_span["parent_span_id"])
        self.assertEqual(recv_mesh_span["span_id"], recv_transport_span["parent_span_id"])
        self.assertEqual(recv_transport_span["span_id"], poll_span["parent_span_id"])
        self.assertEqual(poll_span["span_id"], receive_span["parent_span_id"])
        self.assertEqual(receive_span["span_id"], node2_span["parent_span_id"])
        self.assertEqual(node2_span["span_id"], ack_msg_span["parent_span_id"])
        self.assertEqual(ack_msg_span["span_id"], ack_transport_span["parent_span_id"])
        self.assertEqual(ack_transport_span["span_id"], ack_mesh_span["parent_span_id"])
        self.assertIn("tx.sender_unix_ms", poll_span["attributes"])
        self.assertIn("tx.sender_unix_ms", receive_span["attributes"])
        self.assertIn("tx.message_age_ms", receive_span["attributes"])
        self.assertGreaterEqual(sent_message[Schema.F_TIMESTAMP], 1_700_000_000_000)

    def test_protocol_timestamp_defaults_to_unix_epoch_ms(self):
        from dnet.messaging import MessageCodec, MessagingEndpoint, Schema
        from dnet.signalling.LighthouseTransport import LighthouseMeshTransport
        from otel.api import get_tracer

        codec = MessageCodec()
        mesh = _TracingFakeMesh(get_tracer("dnet.signalling.mesh"), codec)
        transport = LighthouseMeshTransport(mesh, default_peer="node2")
        endpoint = MessagingEndpoint(node_id="node1", transport=transport, codec=codec)

        payload = endpoint.send_event(
            peer_id="node2",
            event_name="sensor.distance.measured",
            parameters={"distance_mm": 100},
            ttl_ms=2500,
        )

        message = codec.decode(payload)
        self.assertGreaterEqual(message[Schema.F_TIMESTAMP], 1_700_000_000_000)


if __name__ == "__main__":
    unittest.main()
