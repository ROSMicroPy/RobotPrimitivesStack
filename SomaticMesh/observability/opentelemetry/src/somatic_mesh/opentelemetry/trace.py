# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
from .context import SpanContext, get_current_span_context, set_current_span
from .util import now_unix_nanos, random_span_id, random_trace_id


# Consult the shared telemetry switch, defaulting to enabled if the API cannot be read.
def _telemetry_enabled():
    try:
        from .api import is_telemetry_enabled

        return is_telemetry_enabled()
    except Exception:
        return True


# Consult the configured span filter, defaulting to emission if the API fails.
def _should_emit_span(name):
    try:
        from .api import should_emit_span

        return should_emit_span(name)
    except Exception:
        return True


class NoOpSpan:
    trace_id = None
    span_id = None
    parent_span_id = None
    start_time_unix_nano = 0
    end_time_unix_nano = 0
    attributes = {}
    events = []
    status_code = 'UNSET'
    status_message = ''

    # Return no propagation context because this span records nothing.
    @property
    def context(self):
        return None

    # Allow disabled tracing to retain the same with-block interface.
    def __enter__(self):
        return self

    # Leave the inert span scope without suppressing application exceptions.
    def __exit__(self, exc_type, exc, tb):
        return False

    # Accept an attribute without retaining or exporting telemetry.
    def set_attribute(self, key, value):
        return True

    # Accept a span event without recording it.
    def add_event(self, name, attributes=None):
        return True

    # Accept a span status change without recording it.
    def set_status(self, code, message=''):
        return True

    # Accept exception instrumentation without recording telemetry.
    def record_exception(self, exc):
        return True

    # Acknowledge span completion without exporting anything.
    def end(self):
        return True

    # Return an empty representation for this non-recording span.
    def to_dict(self):
        return {}


_NOOP_SPAN = NoOpSpan()


class Span:
    # Start timing a named span and prepare its attributes, events, status, and parent identity.
    def __init__(self, tracer, name, trace_id, span_id, parent_span_id=None):
        self._tracer = tracer
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.start_time_unix_nano = now_unix_nanos()
        self.end_time_unix_nano = None
        self.attributes = {}
        self.events = []
        self.status_code = 'UNSET'
        self.status_message = ''
        self._ended = False
        self._previous = None

    # Expose this span's identifiers as a local propagation context.
    @property
    def context(self):
        return SpanContext(trace_id=self.trace_id, span_id=self.span_id, is_remote=False)

    # Make this span current while retaining the previous span for restoration.
    def __enter__(self):
        self._previous = set_current_span(self)
        return self

    # Record an escaping exception, finish the span, and restore its previous context.
    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            self.record_exception(exc)
        self.end()
        set_current_span(self._previous)
        self._previous = None
        return False

    # Attach a named value to the span's diagnostic attributes.
    def set_attribute(self, key, value):
        self.attributes[str(key)] = value

    # Append a timestamped event and its attributes to this span.
    def add_event(self, name, attributes=None):
        self.events.append(
            {
                'name': str(name),
                'time_unix_nano': now_unix_nanos(),
                'attributes': attributes or {},
            }
        )

    # Store the span outcome code and explanatory message.
    def set_status(self, code, message=''):
        self.status_code = str(code)
        self.status_message = str(message)

    # Record exception details as an event and mark the span as failed.
    def record_exception(self, exc):
        self.add_event(
            'exception',
            {
                'exception.type': exc.__class__.__name__,
                'exception.message': str(exc),
            },
        )
        self.set_status('ERROR', str(exc))

    # Finish and publish the span once, provided telemetry remains enabled.
    def end(self):
        if self._ended or not _telemetry_enabled():
            return
        self.end_time_unix_nano = now_unix_nanos()
        self._ended = True
        self._tracer._on_end(self)

    # Project span identity, timing, events, attributes, and status into a dictionary.
    def to_dict(self):
        return {
            'name': self.name,
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'parent_span_id': self.parent_span_id,
            'start_time_unix_nano': self.start_time_unix_nano,
            'end_time_unix_nano': self.end_time_unix_nano,
            'attributes': self.attributes,
            'events': self.events,
            'status': {
                'code': self.status_code,
                'message': self.status_message,
            },
        }


class Tracer:
    # Bind a named instrumentation scope to the provider receiving its finished spans.
    def __init__(self, provider, name):
        self._provider = provider
        self.name = name

    # Honor tracing filters, inherit or create a trace, and construct a new child span.
    def start_span(self, name, parent_context=None, attributes=None, kind=None):
        if not _telemetry_enabled() or not _should_emit_span(name):
            return _NOOP_SPAN
        parent = parent_context or get_current_span_context()
        if parent is None:
            trace_id = random_trace_id()
            parent_span_id = None
        else:
            trace_id = parent.trace_id
            parent_span_id = parent.span_id
        span = Span(
            tracer=self,
            name=name,
            trace_id=trace_id,
            span_id=random_span_id(),
            parent_span_id=parent_span_id,
        )
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        if kind is not None:
            span.set_attribute('span.kind', kind)
        return span

    # Create a span whose context-manager entry will make it current.
    def start_as_current_span(self, name, parent_context=None, attributes=None, kind=None):
        return self.start_span(
            name,
            parent_context=parent_context,
            attributes=attributes,
            kind=kind,
        )

    # Forward a completed span to its provider while telemetry is enabled.
    def _on_end(self, span):
        if not _telemetry_enabled():
            return True
        self._provider._on_end(span)


class NoOpTracer:
    # Retain the instrumentation name for this non-recording telemetry interface.
    def __init__(self, name):
        self.name = name

    # Return the shared inert span so instrumentation can run while tracing is disabled.
    def start_span(self, name, parent_context=None, attributes=None, kind=None):
        return _NOOP_SPAN

    # Return an inert span compatible with the normal tracing context-manager interface.
    def start_as_current_span(self, name, parent_context=None, attributes=None, kind=None):
        return _NOOP_SPAN

    # Ignore completed spans while preserving the processor/provider interface.
    def _on_end(self, span):
        return True


class TracerProvider:
    # Prepare resource metadata, span processors, and finished-span history.
    def __init__(self, resource=None):
        self.resource = resource or {}
        self._processors = []
        self._finished_spans = []

    # Create a named tracer, returning an inert tracer while telemetry is disabled.
    def get_tracer(self, name):
        if not _telemetry_enabled():
            return NoOpTracer(name)
        return Tracer(self, name)

    # Register another consumer of completed spans.
    def add_span_processor(self, processor):
        self._processors.append(processor)

    # Retain a span snapshot and send the completed span to every processor.
    def _on_end(self, span):
        self._finished_spans.append(span.to_dict())
        for processor in self._processors:
            processor.on_end(span, resource=self.resource)

    # Return a copy of the finished-span history list.
    def snapshot(self):
        return list(self._finished_spans)

    # Ask each registered processor to flush and release its resources.
    def shutdown(self):
        for processor in self._processors:
            if hasattr(processor, 'shutdown'):
                processor.shutdown()


class NoOpTracerProvider:
    # Retain resource metadata for a provider that performs no telemetry export.
    def __init__(self, resource=None):
        self.resource = resource or {}

    # Return a named inert tracer so callers can keep their instrumentation path.
    def get_tracer(self, name):
        return NoOpTracer(name)

    # Acknowledge processor registration without enabling span processing.
    def add_span_processor(self, processor):
        return True

    # Ignore completed spans while preserving the processor/provider interface.
    def _on_end(self, span):
        return True

    # Return empty history because this provider retains no spans.
    def snapshot(self):
        return []

    # Acknowledge shutdown; this inert telemetry object owns no export resources.
    def shutdown(self):
        return True
