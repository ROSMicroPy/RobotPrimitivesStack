# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
from .context import get_current_span
from .util import now_unix_nanos


_SEVERITY_ORDER = {
    'DEBUG': 10,
    'INFO': 20,
    'WARN': 30,
    'WARNING': 30,
    'ERROR': 40,
}


# Normalize severity aliases and fall back to DEBUG for unknown levels.
def _normalize_severity(level):
    text = str(level or 'DEBUG').strip().upper()
    if text == 'WARNING':
        return 'WARN'
    if text not in _SEVERITY_ORDER:
        return 'DEBUG'
    return text


# Consult the shared enable switch, defaulting to enabled if the API is unavailable.
def _telemetry_enabled():
    try:
        from .api import is_telemetry_enabled

        return is_telemetry_enabled()
    except Exception:
        return True


class LogRecord:
    # Capture message, severity, attributes, timestamp, and the current span's correlation IDs.
    def __init__(
        self,
        logger,
        severity_text,
        body,
        attributes=None,
        timestamp_unix_nano=None,
        span=None,
    ):
        self.logger_name = logger.name
        self.severity_text = str(severity_text)
        self.body = body
        self.attributes = attributes or {}
        self.timestamp_unix_nano = timestamp_unix_nano or now_unix_nanos()
        current_span = span or get_current_span()
        self.trace_id = None
        self.span_id = None
        if current_span is not None:
            self.trace_id = current_span.trace_id
            self.span_id = current_span.span_id

    # Expose the log record and trace correlation fields as a dictionary.
    def to_dict(self):
        return {
            'logger_name': self.logger_name,
            'severity_text': self.severity_text,
            'body': self.body,
            'attributes': self.attributes,
            'timestamp_unix_nano': self.timestamp_unix_nano,
            'trace_id': self.trace_id,
            'span_id': self.span_id,
        }


class Logger:
    # Bind a named logging scope to the provider that filters and exports its records.
    def __init__(self, provider, name):
        self._provider = provider
        self.name = name

    # Apply enable/severity filters, build a correlated record, and hand it to the provider.
    def emit(self, severity_text, body, attributes=None, span=None, force=False):
        if not _telemetry_enabled():
            return True
        if not self._provider.should_emit(severity_text, force=force):
            return True
        record = LogRecord(self, severity_text, body, attributes=attributes, span=span)
        self._provider._emit(record)
        return record

    # Emit a DEBUG record through the common filtering and correlation path.
    def debug(self, body, attributes=None, force=False):
        return self.emit('DEBUG', body, attributes=attributes, force=force)

    # Emit an INFO record through the common filtering and correlation path.
    def info(self, body, attributes=None, force=False):
        return self.emit('INFO', body, attributes=attributes, force=force)

    # Emit a WARN record through the common filtering and correlation path.
    def warn(self, body, attributes=None, force=False):
        return self.emit('WARN', body, attributes=attributes, force=force)

    # Provide the conventional warning spelling for the WARN logging method.
    def warning(self, body, attributes=None, force=False):
        return self.warn(body, attributes=attributes, force=force)

    # Emit an ERROR record through the common filtering and correlation path.
    def error(self, body, attributes=None, force=False):
        return self.emit('ERROR', body, attributes=attributes, force=force)


class NoOpLogger:
    # Retain the instrumentation name for this non-recording telemetry interface.
    def __init__(self, name):
        self.name = name

    # Accept a log record without recording or exporting it.
    def emit(self, severity_text, body, attributes=None, span=None):
        return True

    # Accept a DEBUG message without recording or exporting a log.
    def debug(self, body, attributes=None):
        return True

    # Accept a INFO message without recording or exporting a log.
    def info(self, body, attributes=None):
        return True

    # Accept a WARN message without recording or exporting a log.
    def warn(self, body, attributes=None):
        return True

    # Accept a WARNING message without recording or exporting a log.
    def warning(self, body, attributes=None):
        return True

    # Accept a ERROR message without recording or exporting a log.
    def error(self, body, attributes=None):
        return True


class LoggerProvider:
    # Prepare logging resource metadata, severity filtering, processors, and the fallback sink.
    def __init__(self, resource=None, min_severity='DEBUG', fallback_handler=None):
        self.resource = resource or {}
        self._processors = []
        self._min_severity = _normalize_severity(min_severity)
        self._fallback_handler = fallback_handler

    # Create a named logger, returning an inert logger when telemetry is disabled.
    def get_logger(self, name):
        if not _telemetry_enabled():
            return NoOpLogger(name)
        return Logger(self, name)

    # Give a processor the current fallback sink before registering it.
    def add_log_processor(self, processor):
        if hasattr(processor, 'set_fallback_handler'):
            processor.set_fallback_handler(self._fallback_handler)
        self._processors.append(processor)

    # Normalize and store the minimum accepted logging severity.
    def set_min_severity(self, level):
        self._min_severity = _normalize_severity(level)
        return self._min_severity

    # Return the provider's current severity threshold.
    def get_min_severity(self):
        return self._min_severity

    # Accept forced records or compare normalized severity against the threshold.
    def should_emit(self, severity_text, force=False):
        if force:
            return True
        level = _normalize_severity(severity_text)
        return _SEVERITY_ORDER.get(level, 10) >= _SEVERITY_ORDER.get(self._min_severity, 10)

    # Update the fallback sink on this provider and compatible processors.
    def set_fallback_handler(self, fallback_handler):
        self._fallback_handler = fallback_handler
        for processor in self._processors:
            if hasattr(processor, 'set_fallback_handler'):
                processor.set_fallback_handler(fallback_handler)
        return True

    # Attempt local fallback delivery without letting sink failures escape.
    def emit_fallback(self, record):
        if not callable(self._fallback_handler):
            return False
        try:
            self._fallback_handler(record)
            return True
        except Exception:
            return False

    # Send an enabled log record to all registered processors with resource metadata.
    def _emit(self, record):
        if not _telemetry_enabled():
            return True
        for processor in self._processors:
            processor.emit(record, resource=self.resource)
        return True

    # Release each registered log processor through its shutdown hook.
    def shutdown(self):
        for processor in self._processors:
            if hasattr(processor, 'shutdown'):
                processor.shutdown()


class NoOpLoggerProvider:
    # Retain resource metadata for a provider that performs no telemetry export.
    def __init__(self, resource=None):
        self.resource = resource or {}

    # Return a named inert logger so callers can keep their instrumentation path.
    def get_logger(self, name):
        return NoOpLogger(name)

    # Acknowledge processor registration without enabling log export.
    def add_log_processor(self, processor):
        return True

    # Ignore log records while preserving the provider interface.
    def _emit(self, record):
        return True

    # Acknowledge shutdown; this inert telemetry object owns no export resources.
    def shutdown(self):
        return True
