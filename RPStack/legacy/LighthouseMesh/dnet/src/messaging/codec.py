import json

from otel.propagation import extract_from_carrier, inject_to_carrier

from .schema import Schema


MAX_SHORT_PACKET_BYTES = Schema.SHORT_PACKET_MAX_BYTES


class MessageValidationError(ValueError):
    """Raised when a message fails schema or type validation."""

    pass


class MessageCodec:
    """Encode, decode, and validate composition protocol messages."""

    TRACE_FIELD_TRACE_ID = "trace_id"
    TRACE_FIELD_SPAN_ID = "span_id"
    TRACE_FIELD_TRACE_FLAGS = "trace_flags"
    TRACE_FIELD_TRACE_ID_COMPACT = "t"
    TRACE_FIELD_SPAN_ID_COMPACT = "s"
    TRACE_FIELD_TRACE_FLAGS_COMPACT = "f"
    TRACE_FIELD_SENDER_UNIX_MS = "sender_unix_ms"
    TRACE_FIELD_SENDER_MONOTONIC_MS = "sender_monotonic_ms"
    TRACE_FIELD_SENDER_DEVICE_MS = "sender_device_ms"
    TRACE_FIELD_SENDER_UNIX_MS_COMPACT = "u"
    TRACE_FIELD_SENDER_MONOTONIC_MS_COMPACT = "m"
    TRACE_FIELD_SENDER_DEVICE_MS_COMPACT = "d"

    def __init__(self, max_short_packet_bytes=MAX_SHORT_PACKET_BYTES):
        self.max_short_packet_bytes = int(max_short_packet_bytes)

    def encode_announce(self, node_id, boot_id, sequence, timestamp_ms, ttl_ms, part_kind, firmware=None):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_ANNOUNCE,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_BOOT_ID: str(boot_id),
            Schema.F_SEQUENCE: int(sequence),
            Schema.F_TIMESTAMP: int(timestamp_ms),
            Schema.F_TTL: int(ttl_ms),
            Schema.F_PART_KIND: str(part_kind),
        }
        if firmware is not None:
            msg[Schema.F_FIRMWARE] = str(firmware)
        return self.encode_message(msg, enforce_short_packet=True)

    def encode_claim(self, node_id, boot_id, sequence, timestamp_ms, ttl_ms, claim_id, part, location, state):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_CLAIM,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_BOOT_ID: str(boot_id),
            Schema.F_SEQUENCE: int(sequence),
            Schema.F_TIMESTAMP: int(timestamp_ms),
            Schema.F_TTL: int(ttl_ms),
            Schema.F_CLAIM_ID: str(claim_id),
            Schema.F_PART: dict(part),
            Schema.F_LOCATION: dict(location),
            Schema.F_STATE: dict(state),
        }
        return self.encode_message(msg)

    def encode_update(self, node_id, boot_id, sequence, timestamp_ms, claim_id, ttl_ms, state):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_UPDATE,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_BOOT_ID: str(boot_id),
            Schema.F_SEQUENCE: int(sequence),
            Schema.F_TIMESTAMP: int(timestamp_ms),
            Schema.F_CLAIM_ID: str(claim_id),
            Schema.F_TTL: int(ttl_ms),
            Schema.F_STATE: dict(state),
        }
        return self.encode_message(msg)

    def encode_withdraw(self, node_id, boot_id, sequence, timestamp_ms, claim_id, reason):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_WITHDRAW,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_BOOT_ID: str(boot_id),
            Schema.F_SEQUENCE: int(sequence),
            Schema.F_TIMESTAMP: int(timestamp_ms),
            Schema.F_CLAIM_ID: str(claim_id),
            Schema.F_REASON: str(reason),
        }
        return self.encode_message(msg)

    def encode_report(self, node_id, boot_id, sequence, timestamp_ms, subject, status, detail=None):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_REPORT,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_BOOT_ID: str(boot_id),
            Schema.F_SEQUENCE: int(sequence),
            Schema.F_TIMESTAMP: int(timestamp_ms),
            Schema.F_SUBJECT: str(subject),
            Schema.F_STATUS: str(status),
        }
        if detail is not None:
            if not isinstance(detail, dict):
                raise MessageValidationError("detail must be an object")
            msg[Schema.F_DETAIL] = detail
        return self.encode_message(msg)

    def encode_event(
        self,
        node_id,
        boot_id,
        sequence,
        timestamp_ms,
        event_name,
        parameters=None,
        priority=None,
        ttl_ms=None,
    ):
        event = {
            Schema.F_EVENT_NAME: str(event_name),
            Schema.F_EVENT_PARAMETERS: dict(parameters or {}),
        }
        if priority is not None:
            event[Schema.F_EVENT_PRIORITY] = str(priority)
        if ttl_ms is not None:
            event[Schema.F_EVENT_TTL] = int(ttl_ms)
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_EVENT,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_BOOT_ID: str(boot_id),
            Schema.F_SEQUENCE: int(sequence),
            Schema.F_TIMESTAMP: int(timestamp_ms),
            Schema.F_EVENT: event,
        }
        return self.encode_message(msg)

    def encode_message(
        self,
        msg,
        trace_context=None,
        trace_fields=None,
        enforce_short_packet=False,
        drop_trace_on_overflow=False,
    ):
        encoded_message = dict(msg)
        if trace_context is not None:
            inject_to_carrier(encoded_message, context=trace_context, field=Schema.F_TRACE)
        if trace_fields:
            carrier = encoded_message.get(Schema.F_TRACE)
            if not isinstance(carrier, dict):
                carrier = {}
                encoded_message[Schema.F_TRACE] = carrier
            for key, value in trace_fields.items():
                carrier[str(key)] = value
        if trace_context is not None or trace_fields:
            self._compact_trace_carrier(encoded_message)
        self.validate(encoded_message)
        self._compact_trace_carrier(encoded_message)
        encoded = self.dumps(encoded_message)
        if enforce_short_packet and len(encoded) > self.max_short_packet_bytes:
            if drop_trace_on_overflow and Schema.F_TRACE in encoded_message:
                del encoded_message[Schema.F_TRACE]
                self.validate(encoded_message)
                encoded = self.dumps(encoded_message)
                if len(encoded) <= self.max_short_packet_bytes:
                    return encoded
            raise MessageValidationError(
                "announce exceeds {} bytes (got {})".format(
                    self.max_short_packet_bytes, len(encoded)
                )
            )
        return encoded

    def decode(self, raw):
        """Parse JSON payload then validate protocol shape and types."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        msg = json.loads(raw)
        self._expand_trace_carrier(msg)
        self.validate(msg)
        return msg

    def extract_trace_context(self, msg):
        self._expand_trace_carrier(msg)
        return extract_from_carrier(msg, field=Schema.F_TRACE)

    def dumps(self, msg):
        """Serialize a message with compact separators."""
        return json.dumps(msg, separators=(",", ":"))

    def validate(self, msg):
        if not isinstance(msg, dict):
            raise MessageValidationError("message must be a JSON object")

        self._expand_trace_carrier(msg)
        self._validate_common(msg)
        mtype = msg[Schema.F_TYPE]
        if mtype == Schema.TYPE_ANNOUNCE:
            self._validate_announce(msg)
        elif mtype == Schema.TYPE_CLAIM:
            self._validate_claim(msg)
        elif mtype == Schema.TYPE_UPDATE:
            self._validate_update(msg)
        elif mtype == Schema.TYPE_WITHDRAW:
            self._validate_withdraw(msg)
        elif mtype == Schema.TYPE_REPORT:
            self._validate_report(msg)
        elif mtype == Schema.TYPE_EVENT:
            self._validate_event(msg)
        else:
            raise MessageValidationError("unsupported message type: {}".format(mtype))

    def _validate_common(self, msg):
        for key in (
            Schema.F_VERSION,
            Schema.F_TYPE,
            Schema.F_NODE_ID,
            Schema.F_BOOT_ID,
            Schema.F_SEQUENCE,
            Schema.F_TIMESTAMP,
        ):
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        if msg[Schema.F_VERSION] != Schema.PROTOCOL_VERSION:
            raise MessageValidationError("unsupported version: {}".format(msg[Schema.F_VERSION]))
        self._validate_non_empty_string(msg[Schema.F_TYPE], Schema.F_TYPE)
        self._validate_non_empty_string(msg[Schema.F_NODE_ID], Schema.F_NODE_ID)
        self._validate_non_empty_string(msg[Schema.F_BOOT_ID], Schema.F_BOOT_ID)
        self._validate_int(msg[Schema.F_SEQUENCE], Schema.F_SEQUENCE, minimum=0)
        self._validate_int(msg[Schema.F_TIMESTAMP], Schema.F_TIMESTAMP, minimum=0)
        if Schema.F_TRACE in msg:
            context = extract_from_carrier(msg, field=Schema.F_TRACE)
            if context is None:
                raise MessageValidationError("field '{}' must be a valid trace context".format(Schema.F_TRACE))

    def _compact_trace_carrier(self, msg):
        trace = msg.get(Schema.F_TRACE)
        if not isinstance(trace, dict):
            return
        trace_id = trace.get(self.TRACE_FIELD_TRACE_ID)
        span_id = trace.get(self.TRACE_FIELD_SPAN_ID)
        trace_flags = trace.get(self.TRACE_FIELD_TRACE_FLAGS, "01")
        compact = {}
        if trace_id:
            compact[self.TRACE_FIELD_TRACE_ID_COMPACT] = trace_id
        if span_id:
            compact[self.TRACE_FIELD_SPAN_ID_COMPACT] = span_id
        if trace_flags and trace_flags != "01":
            compact[self.TRACE_FIELD_TRACE_FLAGS_COMPACT] = trace_flags
        sender_unix_ms = trace.get(self.TRACE_FIELD_SENDER_UNIX_MS)
        if sender_unix_ms is not None:
            compact[self.TRACE_FIELD_SENDER_UNIX_MS_COMPACT] = int(sender_unix_ms)
        sender_monotonic_ms = trace.get(self.TRACE_FIELD_SENDER_MONOTONIC_MS)
        if sender_monotonic_ms is not None:
            compact[self.TRACE_FIELD_SENDER_MONOTONIC_MS_COMPACT] = int(sender_monotonic_ms)
        sender_device_ms = trace.get(self.TRACE_FIELD_SENDER_DEVICE_MS)
        if sender_device_ms is not None:
            compact[self.TRACE_FIELD_SENDER_DEVICE_MS_COMPACT] = int(sender_device_ms)
        for key, value in trace.items():
            if key in (
                self.TRACE_FIELD_TRACE_ID,
                self.TRACE_FIELD_SPAN_ID,
                self.TRACE_FIELD_TRACE_FLAGS,
                self.TRACE_FIELD_SENDER_UNIX_MS,
                self.TRACE_FIELD_SENDER_MONOTONIC_MS,
                self.TRACE_FIELD_SENDER_DEVICE_MS,
            ):
                continue
            compact[key] = value
        if compact:
            msg[Schema.F_TRACE] = compact

    def _expand_trace_carrier(self, msg):
        if not isinstance(msg, dict):
            return
        trace = msg.get(Schema.F_TRACE)
        if not isinstance(trace, dict):
            return
        if self.TRACE_FIELD_TRACE_ID in trace and self.TRACE_FIELD_SPAN_ID in trace:
            return
        trace_id = trace.get(self.TRACE_FIELD_TRACE_ID_COMPACT)
        span_id = trace.get(self.TRACE_FIELD_SPAN_ID_COMPACT)
        if not trace_id or not span_id:
            return
        expanded = {
            self.TRACE_FIELD_TRACE_ID: trace_id,
            self.TRACE_FIELD_SPAN_ID: span_id,
            self.TRACE_FIELD_TRACE_FLAGS: trace.get(self.TRACE_FIELD_TRACE_FLAGS_COMPACT, "01"),
        }
        sender_unix_ms = trace.get(self.TRACE_FIELD_SENDER_UNIX_MS_COMPACT)
        if sender_unix_ms is not None:
            expanded[self.TRACE_FIELD_SENDER_UNIX_MS] = int(sender_unix_ms)
        sender_monotonic_ms = trace.get(self.TRACE_FIELD_SENDER_MONOTONIC_MS_COMPACT)
        if sender_monotonic_ms is not None:
            expanded[self.TRACE_FIELD_SENDER_MONOTONIC_MS] = int(sender_monotonic_ms)
        sender_device_ms = trace.get(self.TRACE_FIELD_SENDER_DEVICE_MS_COMPACT)
        if sender_device_ms is not None:
            expanded[self.TRACE_FIELD_SENDER_DEVICE_MS] = int(sender_device_ms)
        for key, value in trace.items():
            if key in (
                self.TRACE_FIELD_TRACE_ID_COMPACT,
                self.TRACE_FIELD_SPAN_ID_COMPACT,
                self.TRACE_FIELD_TRACE_FLAGS_COMPACT,
                self.TRACE_FIELD_SENDER_UNIX_MS_COMPACT,
                self.TRACE_FIELD_SENDER_MONOTONIC_MS_COMPACT,
                self.TRACE_FIELD_SENDER_DEVICE_MS_COMPACT,
            ):
                continue
            expanded[key] = value
        msg[Schema.F_TRACE] = expanded

    def _validate_announce(self, msg):
        for key in Schema.ANNOUNCE_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        self._validate_int(msg[Schema.F_TTL], Schema.F_TTL, minimum=1)
        self._validate_non_empty_string(msg[Schema.F_PART_KIND], Schema.F_PART_KIND)
        if Schema.F_FIRMWARE in msg:
            self._validate_non_empty_string(msg[Schema.F_FIRMWARE], Schema.F_FIRMWARE)

    def _validate_claim(self, msg):
        for key in Schema.CLAIM_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        self._validate_int(msg[Schema.F_TTL], Schema.F_TTL, minimum=1)
        self._validate_non_empty_string(msg[Schema.F_CLAIM_ID], Schema.F_CLAIM_ID)
        self._validate_part(msg[Schema.F_PART])
        self._validate_location(msg[Schema.F_LOCATION])
        self._validate_state(msg[Schema.F_STATE])

    def _validate_update(self, msg):
        for key in Schema.UPDATE_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        self._validate_non_empty_string(msg[Schema.F_CLAIM_ID], Schema.F_CLAIM_ID)
        self._validate_int(msg[Schema.F_TTL], Schema.F_TTL, minimum=1)
        self._validate_state(msg[Schema.F_STATE])

    def _validate_withdraw(self, msg):
        for key in Schema.WITHDRAW_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        self._validate_non_empty_string(msg[Schema.F_CLAIM_ID], Schema.F_CLAIM_ID)
        self._validate_non_empty_string(msg[Schema.F_REASON], Schema.F_REASON)

    def _validate_report(self, msg):
        for key in Schema.REPORT_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        self._validate_non_empty_string(msg[Schema.F_SUBJECT], Schema.F_SUBJECT)
        self._validate_non_empty_string(msg[Schema.F_STATUS], Schema.F_STATUS)
        if Schema.F_DETAIL in msg and not isinstance(msg[Schema.F_DETAIL], dict):
            raise MessageValidationError("field '{}' must be an object".format(Schema.F_DETAIL))

    def _validate_event(self, msg):
        for key in Schema.EVENT_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        event = msg[Schema.F_EVENT]
        if not isinstance(event, dict):
            raise MessageValidationError("field '{}' must be an object".format(Schema.F_EVENT))
        if Schema.F_EVENT_NAME not in event:
            raise MessageValidationError("event missing '{}'".format(Schema.F_EVENT_NAME))
        self._validate_non_empty_string(
            event[Schema.F_EVENT_NAME],
            "event.{}".format(Schema.F_EVENT_NAME),
        )
        if Schema.F_EVENT_PRIORITY in event:
            self._validate_non_empty_string(
                event[Schema.F_EVENT_PRIORITY],
                "event.{}".format(Schema.F_EVENT_PRIORITY),
            )
            if event[Schema.F_EVENT_PRIORITY] not in Schema.EVENT_PRIORITIES:
                raise MessageValidationError("unsupported event priority: {}".format(event[Schema.F_EVENT_PRIORITY]))
        if Schema.F_EVENT_TTL in event:
            self._validate_int(
                event[Schema.F_EVENT_TTL],
                "event.{}".format(Schema.F_EVENT_TTL),
                minimum=1,
            )
        if Schema.F_EVENT_PARAMETERS in event:
            if not isinstance(event[Schema.F_EVENT_PARAMETERS], dict):
                raise MessageValidationError(
                    "field 'event.{}' must be an object".format(Schema.F_EVENT_PARAMETERS)
                )
        else:
            raise MessageValidationError("event missing '{}'".format(Schema.F_EVENT_PARAMETERS))

    def _validate_part(self, part):
        if not isinstance(part, dict):
            raise MessageValidationError("field '{}' must be an object".format(Schema.F_PART))
        if Schema.F_KIND not in part:
            raise MessageValidationError("part missing '{}'".format(Schema.F_KIND))
        self._validate_non_empty_string(part[Schema.F_KIND], "part.{}".format(Schema.F_KIND))
        if Schema.F_DOFS in part:
            dofs = part[Schema.F_DOFS]
            if not isinstance(dofs, list):
                raise MessageValidationError("field 'part.{}' must be an array".format(Schema.F_DOFS))
            for dof in dofs:
                self._validate_dof(dof)
        for key in (Schema.F_CONTROL_MODES, Schema.F_FEEDBACK_MODES):
            if key in part:
                values = part[key]
                if not isinstance(values, list):
                    raise MessageValidationError("field 'part.{}' must be an array".format(key))
                for value in values:
                    self._validate_non_empty_string(value, "part.{}".format(key))

    def _validate_dof(self, dof):
        if not isinstance(dof, dict):
            raise MessageValidationError("dof entries must be objects")
        for key in (Schema.F_DOF_ID, Schema.F_DOF_KIND, Schema.F_DOF_AXIS):
            if key not in dof:
                raise MessageValidationError("dof missing '{}'".format(key))
            self._validate_non_empty_string(dof[key], "dof.{}".format(key))
        for key in (
            Schema.F_DOF_MIN,
            Schema.F_DOF_MAX,
            Schema.F_DOF_MAX_VELOCITY,
            Schema.F_DOF_MAX_ACCELERATION,
            Schema.F_DOF_RESOLUTION,
        ):
            if key in dof and not isinstance(dof[key], (int, float)):
                raise MessageValidationError("field 'dof.{}' must be numeric".format(key))
        if Schema.F_DOF_UNIT in dof:
            self._validate_non_empty_string(dof[Schema.F_DOF_UNIT], "dof.{}".format(Schema.F_DOF_UNIT))

    def _validate_location(self, location):
        if not isinstance(location, dict):
            raise MessageValidationError("field '{}' must be an object".format(Schema.F_LOCATION))
        if Schema.F_LOCATION_ID not in location:
            raise MessageValidationError("location missing '{}'".format(Schema.F_LOCATION_ID))
        self._validate_non_empty_string(
            location[Schema.F_LOCATION_ID],
            "location.{}".format(Schema.F_LOCATION_ID),
        )
        if Schema.F_LOCATION_CONFIDENCE in location:
            self._validate_int(
                location[Schema.F_LOCATION_CONFIDENCE],
                "location.{}".format(Schema.F_LOCATION_CONFIDENCE),
                minimum=0,
                maximum=100,
            )
        for key in (
            Schema.F_LOCATION_PARENT,
            Schema.F_LOCATION_FAMILY,
            Schema.F_LOCATION_SOURCE,
            Schema.F_LOCATION_ORIENTATION,
        ):
            if key in location:
                self._validate_non_empty_string(location[key], "location.{}".format(key))

    def _validate_state(self, state):
        if not isinstance(state, dict):
            raise MessageValidationError("field '{}' must be an object".format(Schema.F_STATE))
        for key in (
            Schema.F_STATE_CALIBRATION,
            Schema.F_STATE_HEALTH,
            Schema.F_STATE_CONFIDENCE,
        ):
            if key not in state:
                raise MessageValidationError("state missing '{}'".format(key))
        self._validate_non_empty_string(
            state[Schema.F_STATE_CALIBRATION],
            "state.{}".format(Schema.F_STATE_CALIBRATION),
        )
        self._validate_non_empty_string(
            state[Schema.F_STATE_HEALTH],
            "state.{}".format(Schema.F_STATE_HEALTH),
        )
        self._validate_int(
            state[Schema.F_STATE_CONFIDENCE],
            "state.{}".format(Schema.F_STATE_CONFIDENCE),
            minimum=0,
            maximum=100,
        )
        if Schema.F_STATE_FAULTS in state:
            faults = state[Schema.F_STATE_FAULTS]
            if not isinstance(faults, list):
                raise MessageValidationError("field 'state.{}' must be an array".format(Schema.F_STATE_FAULTS))
            for fault in faults:
                self._validate_non_empty_string(fault, "state.{}".format(Schema.F_STATE_FAULTS))
        for key in (Schema.F_STATE_TEMPERATURE, Schema.F_STATE_SUPPLY):
            if key in state and not isinstance(state[key], (int, float)):
                raise MessageValidationError("field 'state.{}' must be numeric".format(key))

    @staticmethod
    def _validate_non_empty_string(value, name):
        if not isinstance(value, str) or not value:
            raise MessageValidationError("field '{}' must be a non-empty string".format(name))

    @staticmethod
    def _validate_int(value, name, minimum=None, maximum=None):
        if not isinstance(value, int):
            raise MessageValidationError("field '{}' must be an int".format(name))
        if minimum is not None and value < minimum:
            raise MessageValidationError("field '{}' must be >= {}".format(name, minimum))
        if maximum is not None and value > maximum:
            raise MessageValidationError("field '{}' must be <= {}".format(name, maximum))
