import json

from otel.api import get_tracer
from otel.context import SpanContext


class LighthouseMeshTransport:
    """
    Adapter between dnet.messaging.MessagingEndpoint and LighthouseMesh.

    Implements the transport contract expected by MessagingEndpoint:
    - send(peer_id, payload)
    - recv() -> (peer_id, payload) or (None, None)
    """

    def __init__(self, mesh, default_peer=None):
        self.mesh = mesh
        self.default_peer = default_peer
        self.tracer = get_tracer("dnet.signalling.transport")
        self._last_recv_context = None
        self._last_recv_metadata = None

    def send(self, peer_id, payload, message=None):
        peer = self.default_peer if peer_id is None else peer_id
        attributes = {
            "peer_id": str(peer),
            "transport": "espnow",
        }
        if isinstance(message, dict):
            attributes["message.type"] = str(message.get("t", "unknown"))
        with self.tracer.start_span("dnet.signalling.transport.send", attributes=attributes, kind="internal") as span:
            if payload is not None:
                span.set_attribute("message.bytes", len(payload))
            self.mesh.send_raw(peer, payload)

    def recv(self):
        mac, payload = self.mesh.recv_raw(timeout_ms=0)
        if payload is None:
            return None, None
        consume_context = getattr(self.mesh, "consume_recv_trace_context", None)
        if callable(consume_context):
            parent_context = consume_context()
        else:
            parent_context = None
        consume_metadata = getattr(self.mesh, "consume_recv_metadata", None)
        if callable(consume_metadata):
            metadata = consume_metadata() or {}
        else:
            metadata = {}
        if parent_context is None:
            parent_context = self._extract_payload_context(payload)
        trace_metadata = self._extract_trace_metadata(payload)
        peer_id = self.mesh.mac_to_node_id(mac)
        attributes = {"peer_id": str(peer_id), "transport": "espnow"}
        if metadata.get("queued_ms") is not None:
            attributes["rx.queue_ms"] = int(metadata["queued_ms"])
        if metadata.get("ingest_source") is not None:
            attributes["rx.ingest_source"] = str(metadata["ingest_source"])
        if trace_metadata.get("sender_unix_ms") is not None:
            attributes["tx.sender_unix_ms"] = int(trace_metadata["sender_unix_ms"])
        if trace_metadata.get("sender_device_ms") is not None:
            attributes["tx.sender_device_ms"] = int(trace_metadata["sender_device_ms"])
        if trace_metadata.get("sender_monotonic_ms") is not None:
            attributes["tx.sender_monotonic_ms"] = int(trace_metadata["sender_monotonic_ms"])
        with self.tracer.start_span(
            "dnet.signalling.transport.recv",
            parent_context=parent_context,
            attributes=attributes,
            kind="internal",
        ) as span:
            self._last_recv_context = span.context
            self._last_recv_metadata = dict(metadata)
            span.set_attribute("message.bytes", len(payload))
        return peer_id, payload

    def consume_recv_trace_context(self):
        context = self._last_recv_context
        self._last_recv_context = None
        return context

    def consume_recv_metadata(self):
        metadata = self._last_recv_metadata
        self._last_recv_metadata = None
        return metadata

    @staticmethod
    def _extract_payload_context(payload):
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        try:
            message = json.loads(payload)
        except Exception:
            return None
        carrier = message.get("otel")
        if not isinstance(carrier, dict):
            return None
        trace_id = carrier.get("trace_id") or carrier.get("t")
        span_id = carrier.get("span_id") or carrier.get("s")
        if not trace_id or not span_id:
            return None
        return SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=carrier.get("trace_flags") or carrier.get("f") or "01",
            is_remote=True,
        )

    @staticmethod
    def _extract_trace_metadata(payload):
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        try:
            message = json.loads(payload)
        except Exception:
            return {}
        carrier = message.get("otel")
        if not isinstance(carrier, dict):
            return {}
        return {
            "sender_unix_ms": carrier.get("sender_unix_ms") or carrier.get("u"),
            "sender_device_ms": carrier.get("sender_device_ms") or carrier.get("d"),
            "sender_monotonic_ms": carrier.get("sender_monotonic_ms") or carrier.get("m"),
        }
