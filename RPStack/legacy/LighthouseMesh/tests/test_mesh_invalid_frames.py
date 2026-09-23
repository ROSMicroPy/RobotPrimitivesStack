import importlib.util
import binascii
import pathlib
import sys
import types
import unittest
from contextlib import contextmanager


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


def _load_module(name, module_path):
    if name in sys.modules:
        del sys.modules[name]
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
        return False

    def config(self, *args, **kwargs):
        if args and args[0] == "mac":
            return b"\x80\x65\x99\xdf\x5e\x80"
        return 6


class _MismatchWLAN(_FakeWLAN):
    def config(self, *args, **kwargs):
        if args and args[0] == "mac":
            return b"\x80\x65\x99\xdf\x5e\x80"
        if args and args[0] == "channel":
            return 3
        return 3


class _FakeAIOESPNow:
    def __init__(self):
        self._frames = []

    def active(self, *_args, **_kwargs):
        return True

    def add_peer(self, *_args, **_kwargs):
        return None

    def get_peers(self):
        return ()

    def irq(self, *_args, **_kwargs):
        return None

    def stats(self):
        return (0, 0, 0, 0, 0)

    def irecv(self, timeout_ms=0):
        if self._frames:
            return self._frames.pop(0)
        return None, None


class _FakeEndpoint:
    def __init__(self, invalid_error, valid_message):
        self._steps = [invalid_error, ("node1", valid_message), (None, None)]

    def poll(self):
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    @contextmanager
    def message_context(self, peer_id, message):
        yield


class MeshInvalidFrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _load_package("otel", OTEL_ROOT / "__init__.py", OTEL_ROOT)
        _ensure_namespace_package("dnet", DNET_ROOT)
        _ensure_namespace_package("dnet.signalling", DNET_ROOT / "signalling")
        _ensure_namespace_package("dnet.messaging", DNET_ROOT / "messaging")

        network_module = types.ModuleType("network")
        network_module.STA_IF = 0
        network_module.WLAN = lambda *_args, **_kwargs: _FakeWLAN()
        sys.modules["network"] = network_module

        aioespnow_module = types.ModuleType("aioespnow")
        aioespnow_module.AIOESPNow = _FakeAIOESPNow
        sys.modules["aioespnow"] = aioespnow_module

        ubinascii_module = types.ModuleType("ubinascii")
        ubinascii_module.hexlify = binascii.hexlify
        ubinascii_module.unhexlify = binascii.unhexlify
        sys.modules["ubinascii"] = ubinascii_module

        cls.protocol = _load_module("dnet.messaging.protocol", DNET_ROOT / "messaging" / "protocol.py")
        cls.mesh_module = _load_module(
            "dnet.signalling.LighthouseMesh",
            DNET_ROOT / "signalling" / "LighthouseMesh.py",
        )

    def test_invalid_frame_does_not_block_valid_message(self):
        from otel.api import get_tracer

        mesh = object.__new__(self.mesh_module.LighthouseMesh)
        errors = []
        received = []
        mesh._log_error = errors.append
        mesh.tracer = get_tracer("dnet.signalling.mesh")

        invalid = self.protocol.IncomingMessageError(
            peer_id="bad-peer",
            payload=b"\xff\x00garbage",
            cause=ValueError("syntax error in JSON"),
        )
        endpoint = _FakeEndpoint(
            invalid_error=invalid,
            valid_message={"t": "event", "n": "node1"},
        )

        mesh._drain_endpoint_messages(
            endpoint,
            on_message=lambda peer_id, message: received.append((peer_id, message)),
        )

        self.assertEqual([("node1", {"t": "event", "n": "node1"})], received)
        self.assertEqual(1, len(errors))
        self.assertIn("dropped invalid frame", errors[0])
        self.assertIn("bad-peer", errors[0])
        self.assertIn("syntax error in JSON", errors[0])

    def test_recv_raw_copies_mutable_driver_buffer(self):
        mesh = self.mesh_module.LighthouseMesh(channel=6)
        shared_payload = bytearray(b'{"v":1,"t":"announce"}')
        mac = b"\x80\x65\x99\xdf\x5e\x80"
        mesh.espnow._frames = [(mac, shared_payload)]

        recv_mac, payload = mesh.recv_raw(timeout_ms=0)
        shared_payload[:] = b"\x7fM\x01\x00A\x03\x02corrupted"

        self.assertEqual(mac, recv_mac)
        self.assertIsInstance(payload, bytes)
        self.assertEqual(b'{"v":1,"t":"announce"}', payload)

    def test_irq_drain_is_not_recursive_when_reentered(self):
        mesh = object.__new__(self.mesh_module.LighthouseMesh)
        mesh._irq_count = 0
        mesh._irq_draining = False
        mesh._irq_redrain_requested = False
        drain_calls = []
        pump_calls = []

        def fake_drain():
            drain_calls.append("drain")
            if len(drain_calls) == 1:
                mesh._on_espnow_irq()

        mesh._drain_incoming = fake_drain
        mesh._pump_tx_queue = lambda source: pump_calls.append(source)

        mesh._on_espnow_irq()

        self.assertEqual(2, mesh._irq_count)
        self.assertEqual(["drain", "drain"], drain_calls)
        self.assertEqual(["irq", "irq"], pump_calls)
        self.assertFalse(mesh._irq_draining)
        self.assertFalse(mesh._irq_redrain_requested)

    def test_fragment_expiry_is_not_reentrant(self):
        mesh = object.__new__(self.mesh_module.LighthouseMesh)
        mesh._fragment_buffers = {
            ("peer", 1): {"updated_ms": 0, "parts": {0: b"x"}, "total": 1},
        }
        mesh._FRAG_REASSEMBLY_TIMEOUT_MS = 1
        mesh._fragment_expiry_running = True
        mesh._now_ms = lambda: 100
        mesh._ticks_diff = lambda newer, older: newer - older
        mesh._log_debug = lambda *_args, **_kwargs: None

        mesh._expire_fragment_buffers()

        self.assertEqual(1, len(mesh._fragment_buffers))
        self.assertTrue(mesh._fragment_expiry_running)

    def test_trace_recv_tolerates_suppressed_span_context(self):
        from otel.api import set_trace_detail_mode

        mesh = self.mesh_module.LighthouseMesh(channel=6)
        try:
            set_trace_detail_mode("essential", essential_prefixes=("node2.",))
            mesh._trace_recv(
                b"\x80\x65\x99\xdf\x5e\x80",
                b'{"v":2,"t":"e","n":"node1","b":"boot","q":1,"ts":1,"event":{"name":"sensor.distance.measured","parameters":{"distance_mm":1}}}',
                {"ingest_source": "test", "queued_ms": 0},
            )
            metadata = mesh.consume_recv_metadata()
            self.assertIsNotNone(metadata)
            self.assertEqual(0, metadata.get("queued_ms"))
            self.assertNotIn("recv_span_id", metadata)
        finally:
            set_trace_detail_mode("diagnostic", essential_prefixes=("node2.",))

    def test_mesh_init_fails_fast_on_channel_mismatch(self):
        original_network = self.mesh_module.network
        network_module = types.SimpleNamespace(STA_IF=0, WLAN=lambda *_args, **_kwargs: _MismatchWLAN())
        self.mesh_module.network = network_module
        try:
            self.mesh_module.LighthouseMesh._instance = None
            with self.assertRaises(RuntimeError) as ctx:
                self.mesh_module.LighthouseMesh(channel=6)
            self.assertIn("ESP-NOW channel mismatch", str(ctx.exception))
        finally:
            self.mesh_module.network = original_network
            self.mesh_module.LighthouseMesh._instance = None


if __name__ == "__main__":
    unittest.main()
