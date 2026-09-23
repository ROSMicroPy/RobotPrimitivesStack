import time

from otel.api import get_meter, get_tracer
from otel.util import now_unix_nanos

from .codec import MessageCodec
from .registry import CompositionRegistry
from .schema import Schema


class IncomingMessageError(ValueError):
    """Raised when an inbound transport frame cannot be decoded as a protocol message."""

    def __init__(self, peer_id, payload, cause):
        self.peer_id = peer_id
        self.payload = payload
        self.cause = cause
        super().__init__(str(cause))


class MessagingEndpoint:
    """
    Transport adapter for sending and receiving composition protocol messages.

    Expected transport methods:
    - send(peer_id, payload_str_or_bytes)
    - recv() -> (peer_id, payload_str_or_bytes) or (None, None)
    """

    def __init__(self, node_id, transport, codec=None, registry=None, boot_id=None, tracer=None, meter=None):
        self.node_id = str(node_id)
        self.transport = transport
        self.codec = codec or MessageCodec()
        self.registry = registry or CompositionRegistry()
        self.boot_id = str(boot_id or self._make_boot_id())
        self.tracer = tracer or get_tracer("dnet.messaging")
        self.meter = meter or get_meter("dnet.messaging")
        self._sequence = 0
        self._event_listeners = {}
        self._message_counters = {}
        self._last_receive_context = None
        self._last_receive_metadata = None

    @staticmethod
    def _monotonic_ms():
        ticks_ms = getattr(time, "ticks_ms", None)
        if callable(ticks_ms):
            try:
                return int(ticks_ms())
            except Exception:
                pass
        return int(time.time() * 1000)

    @classmethod
    def _clock_snapshot(cls):
        return {
            "unix_ms": int(now_unix_nanos() // 1_000_000),
            "device_ms": int(time.time() * 1000),
            "monotonic_ms": cls._monotonic_ms(),
        }

    def _trace_timing_fields(self, snapshot):
        return {}

    def _merge_trace_timing_attributes(self, attributes, message, snapshot=None):
        trace = message.get(Schema.F_TRACE) or {}
        sender_unix_ms = message.get(Schema.F_TIMESTAMP)
        sender_monotonic_ms = trace.get(self.codec.TRACE_FIELD_SENDER_MONOTONIC_MS)
        sender_device_ms = trace.get(self.codec.TRACE_FIELD_SENDER_DEVICE_MS)
        current_snapshot = snapshot or self._clock_snapshot()
        if sender_unix_ms is not None:
            sender_unix_ms = int(sender_unix_ms)
            attributes["tx.sender_unix_ms"] = sender_unix_ms
            attributes["tx.observed_clock_offset_ms"] = int(current_snapshot["unix_ms"]) - sender_unix_ms
        if sender_device_ms is not None:
            attributes["tx.sender_device_ms"] = int(sender_device_ms)
        if sender_monotonic_ms is not None:
            attributes["tx.sender_monotonic_ms"] = int(sender_monotonic_ms)
        message_timestamp_ms = message.get(Schema.F_TIMESTAMP)
        if message_timestamp_ms is not None:
            try:
                attributes["tx.message_age_ms"] = int(current_snapshot["unix_ms"]) - int(message_timestamp_ms)
            except Exception:
                pass
        return attributes

    def send_announce(self, peer_id, ttl_ms, part_kind, firmware=None, timestamp_ms=None):
        message = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_ANNOUNCE,
            Schema.F_NODE_ID: str(self.node_id),
            Schema.F_BOOT_ID: str(self.boot_id),
            Schema.F_SEQUENCE: int(self._next_sequence()),
            Schema.F_TIMESTAMP: self._timestamp_ms(timestamp_ms),
            Schema.F_TTL: int(ttl_ms),
            Schema.F_PART_KIND: str(part_kind),
        }
        if firmware is not None:
            message[Schema.F_FIRMWARE] = str(firmware)
        return self._send_message(
            peer_id=peer_id,
            message=message,
            span_name="dnet.messaging.send.announce",
            enforce_short_packet=True,
            drop_trace_on_overflow=True,
        )

    def send_claim(self, peer_id, ttl_ms, claim_id, part, location, state, timestamp_ms=None):
        message = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_CLAIM,
            Schema.F_NODE_ID: str(self.node_id),
            Schema.F_BOOT_ID: str(self.boot_id),
            Schema.F_SEQUENCE: int(self._next_sequence()),
            Schema.F_TIMESTAMP: self._timestamp_ms(timestamp_ms),
            Schema.F_TTL: int(ttl_ms),
            Schema.F_CLAIM_ID: str(claim_id),
            Schema.F_PART: dict(part),
            Schema.F_LOCATION: dict(location),
            Schema.F_STATE: dict(state),
        }
        return self._send_message(
            peer_id=peer_id,
            message=message,
            span_name="dnet.messaging.send.claim",
        )

    def send_update(self, peer_id, claim_id, ttl_ms, state, timestamp_ms=None):
        message = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_UPDATE,
            Schema.F_NODE_ID: str(self.node_id),
            Schema.F_BOOT_ID: str(self.boot_id),
            Schema.F_SEQUENCE: int(self._next_sequence()),
            Schema.F_TIMESTAMP: self._timestamp_ms(timestamp_ms),
            Schema.F_CLAIM_ID: str(claim_id),
            Schema.F_TTL: int(ttl_ms),
            Schema.F_STATE: dict(state),
        }
        return self._send_message(
            peer_id=peer_id,
            message=message,
            span_name="dnet.messaging.send.update",
        )

    def send_withdraw(self, peer_id, claim_id, reason, timestamp_ms=None):
        message = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_WITHDRAW,
            Schema.F_NODE_ID: str(self.node_id),
            Schema.F_BOOT_ID: str(self.boot_id),
            Schema.F_SEQUENCE: int(self._next_sequence()),
            Schema.F_TIMESTAMP: self._timestamp_ms(timestamp_ms),
            Schema.F_CLAIM_ID: str(claim_id),
            Schema.F_REASON: str(reason),
        }
        return self._send_message(
            peer_id=peer_id,
            message=message,
            span_name="dnet.messaging.send.withdraw",
        )

    def send_report(self, peer_id, subject, status, detail=None, timestamp_ms=None):
        message = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_REPORT,
            Schema.F_NODE_ID: str(self.node_id),
            Schema.F_BOOT_ID: str(self.boot_id),
            Schema.F_SEQUENCE: int(self._next_sequence()),
            Schema.F_TIMESTAMP: self._timestamp_ms(timestamp_ms),
            Schema.F_SUBJECT: str(subject),
            Schema.F_STATUS: str(status),
        }
        if detail is not None:
            message[Schema.F_DETAIL] = dict(detail)
        return self._send_message(
            peer_id=peer_id,
            message=message,
            span_name="dnet.messaging.send.report",
        )

    def send_event(
        self,
        peer_id,
        event_name,
        parameters=None,
        priority=Schema.EVENT_PRIORITY_NORMAL,
        ttl_ms=None,
        timestamp_ms=None,
    ):
        event = {
            Schema.F_EVENT_NAME: str(event_name),
            Schema.F_EVENT_PARAMETERS: dict(parameters or {}),
        }
        if priority is not None:
            event[Schema.F_EVENT_PRIORITY] = str(priority)
        if ttl_ms is not None:
            event[Schema.F_EVENT_TTL] = int(ttl_ms)
        message = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_EVENT,
            Schema.F_NODE_ID: str(self.node_id),
            Schema.F_BOOT_ID: str(self.boot_id),
            Schema.F_SEQUENCE: int(self._next_sequence()),
            Schema.F_TIMESTAMP: self._timestamp_ms(timestamp_ms),
            Schema.F_EVENT: event,
        }
        return self._send_message(
            peer_id=peer_id,
            message=message,
            span_name="dnet.messaging.send.event",
        )

    def poll(self):
        """
        Receive one message, decode it, and update local composition state.
        Returns (peer_id, decoded_message) or (None, None).
        """
        peer_id, payload = self.transport.recv()
        if payload is None:
            return None, None

        try:
            parent_context = self._consume_transport_receive_context()
            if parent_context is None:
                message = self.codec.decode(payload)
                parent_context = self.codec.extract_trace_context(message)
            else:
                message = None

            span_attributes = {
                "peer_id": str(peer_id),
                "message.direction": "received",
            }
            metadata = self._consume_transport_receive_metadata() or {}
            if metadata.get("queued_ms") is not None:
                span_attributes["rx.queue_ms"] = int(metadata["queued_ms"])
            if metadata.get("ingest_source") is not None:
                span_attributes["rx.ingest_source"] = str(metadata["ingest_source"])
            with self.tracer.start_span(
                "dnet.messaging.poll",
                parent_context=parent_context,
                attributes=span_attributes,
                kind="internal",
            ) as span:
                if message is None:
                    message = self.codec.decode(payload)
                current_snapshot = self._clock_snapshot()
                self._merge_trace_timing_attributes(span_attributes, message, snapshot=current_snapshot)
                message_type = message.get(Schema.F_TYPE, "unknown")
                for key, value in span_attributes.items():
                    if key in ("peer_id", "message.direction"):
                        continue
                    span.set_attribute(key, value)
                span.set_attribute("message.type", str(message_type))
                span.set_attribute("message.bytes", len(payload))
                self._record_message_metric("received", message)
                self._apply_message(message)
                self._last_receive_context = span.context
                self._last_receive_metadata = dict(metadata)
        except Exception as exc:
            raise IncomingMessageError(peer_id=peer_id, payload=payload, cause=exc)
        return peer_id, message

    def message_context(self, peer_id, message):
        message_type = message.get(Schema.F_TYPE, "unknown")
        parent_context = self._last_receive_context
        self._last_receive_context = None
        if parent_context is None:
            parent_context = self.codec.extract_trace_context(message)
        attributes = {
            "peer_id": str(peer_id),
            "message.type": str(message_type),
            "message.direction": "received",
        }
        metadata = self._last_receive_metadata
        self._last_receive_metadata = None
        if metadata:
            if metadata.get("queued_ms") is not None:
                attributes["rx.queue_ms"] = int(metadata["queued_ms"])
            if metadata.get("ingest_source") is not None:
                attributes["rx.ingest_source"] = str(metadata["ingest_source"])
        self._merge_trace_timing_attributes(attributes, message)
        return self.tracer.start_span(
            "dnet.messaging.receive",
            parent_context=parent_context,
            attributes=attributes,
            kind="consumer",
        )

    def _apply_message(self, message):
        mtype = message[Schema.F_TYPE]
        if mtype == Schema.TYPE_ANNOUNCE:
            self.registry.register_announce(message)
        elif mtype == Schema.TYPE_CLAIM:
            self.registry.register_claim(message)
        elif mtype == Schema.TYPE_UPDATE:
            self.registry.register_update(message)
        elif mtype == Schema.TYPE_WITHDRAW:
            self.registry.register_withdraw(message)
        elif mtype == Schema.TYPE_REPORT:
            self.registry.register_report(message)
        elif mtype == Schema.TYPE_EVENT:
            self.registry.register_event(message)
            self._dispatch_event(message)

    def active_claims(self, now_ms=None):
        return self.registry.active_claims(now_ms=now_ms)

    def resolve_location(self, location_id, now_ms=None):
        return self.registry.resolve_location(location_id, now_ms=now_ms)

    def claims_for_location(self, location_id, now_ms=None):
        return self.registry.claims_for_location(location_id, now_ms=now_ms)

    def get_claim(self, claim_id, now_ms=None):
        return self.registry.get_claim(claim_id, now_ms=now_ms)

    def events(self, event_name=None, now_ms=None, include_expired=False):
        return self.registry.events(
            event_name=event_name,
            now_ms=now_ms,
            include_expired=include_expired,
        )

    def latest_event(self, event_name=None, now_ms=None, include_expired=False):
        return self.registry.latest_event(
            event_name=event_name,
            now_ms=now_ms,
            include_expired=include_expired,
        )

    def add_event_listener(self, event_name, callback):
        listeners = self._event_listeners.get(event_name, [])
        listeners.append(callback)
        self._event_listeners[event_name] = listeners
        return callback

    def remove_event_listener(self, event_name, callback):
        listeners = self._event_listeners.get(event_name, [])
        filtered = []
        for listener in listeners:
            if listener != callback:
                filtered.append(listener)
        self._event_listeners[event_name] = filtered

    def _dispatch_event(self, message):
        event = message.get(Schema.F_EVENT) or {}
        event_name = event.get(Schema.F_EVENT_NAME)
        if not event_name:
            return
        listeners = list(self._event_listeners.get(event_name, []))
        wildcard = list(self._event_listeners.get("*", []))
        for callback in listeners + wildcard:
            callback(message)

    def _next_sequence(self):
        self._sequence += 1
        return self._sequence

    def _send_message(
        self,
        peer_id,
        message,
        span_name,
        enforce_short_packet=False,
        drop_trace_on_overflow=False,
    ):
        message_type = message.get(Schema.F_TYPE, "unknown")
        attributes = {
            "peer_id": str(peer_id),
            "message.type": str(message_type),
            "message.direction": "sent",
        }
        clock_snapshot = self._clock_snapshot()
        with self.tracer.start_span(span_name, attributes=attributes, kind="producer") as span:
            payload = self.codec.encode_message(
                message,
                trace_context=span.context,
                enforce_short_packet=enforce_short_packet,
                drop_trace_on_overflow=drop_trace_on_overflow,
            )
            self.transport.send(peer_id, payload, message=message)
            span.set_attribute("message.bytes", len(payload))
            span.set_attribute("tx.sender_unix_ms", int(clock_snapshot["unix_ms"]))
            span.set_attribute("tx.sender_device_ms", int(clock_snapshot["device_ms"]))
            span.set_attribute("tx.sender_monotonic_ms", int(clock_snapshot["monotonic_ms"]))
        self._record_message_metric("sent", message)
        return payload

    def _record_message_metric(self, direction, message):
        message_type = message.get(Schema.F_TYPE, "unknown")
        counter_name = "dnet.messages.{}.{}.count".format(direction, message_type)
        counter = self._message_counters.get(counter_name)
        if counter is None:
            counter = self.meter.create_counter(counter_name)
            self._message_counters[counter_name] = counter
        counter.add(
            1,
            attributes={
                "message.type": str(message_type),
                "message.direction": str(direction),
            },
        )

    def _consume_transport_receive_context(self):
        consume_context = getattr(self.transport, "consume_recv_trace_context", None)
        if callable(consume_context):
            return consume_context()
        return None

    def _consume_transport_receive_metadata(self):
        consume_metadata = getattr(self.transport, "consume_recv_metadata", None)
        if callable(consume_metadata):
            return consume_metadata()
        return None

    @staticmethod
    def _make_boot_id():
        return "{:x}".format(int(time.time() * 1000) & 0xFFFFFFFF)

    @staticmethod
    def _timestamp_ms(timestamp_ms):
        if timestamp_ms is not None:
            return int(timestamp_ms)
        return int(now_unix_nanos() // 1_000_000)
