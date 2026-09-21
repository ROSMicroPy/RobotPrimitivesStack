
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
_CURRENT_SPAN = None


class SpanContext:
    def __init__(self, trace_id, span_id, trace_flags="01", is_remote=False):
        self.trace_id = str(trace_id)
        self.span_id = str(span_id)
        self.trace_flags = str(trace_flags)
        self.is_remote = bool(is_remote)

    def is_valid(self):
        return bool(self.trace_id and self.span_id)

    def to_carrier(self):
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "trace_flags": self.trace_flags,
        }


class _SpanContextScope:
    def __init__(self, context):
        self._context = context
        self._previous = None

    def __enter__(self):
        self._previous = set_current_span(self._context)
        return self._context

    def __exit__(self, exc_type, exc, tb):
        set_current_span(self._previous)
        return False


def get_current_span():
    return _CURRENT_SPAN


def set_current_span(span):
    global _CURRENT_SPAN
    previous = _CURRENT_SPAN
    _CURRENT_SPAN = span
    return previous


def get_current_span_context():
    current = get_current_span()
    if current is None:
        return None
    if isinstance(current, SpanContext):
        return current
    if hasattr(current, "context"):
        return current.context
    trace_id = getattr(current, "trace_id", None)
    span_id = getattr(current, "span_id", None)
    if not trace_id or not span_id:
        return None
    return SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        trace_flags=getattr(current, "trace_flags", "01"),
        is_remote=getattr(current, "is_remote", False),
    )


def attach_span_context(context):
    return _SpanContextScope(context)
