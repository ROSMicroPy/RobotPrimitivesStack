
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
from .context import SpanContext, get_current_span, get_current_span_context


def inject_traceparent(headers, span=None):
    target = headers if headers is not None else {}
    current = span or get_current_span_context()
    if current is None:
        return target
    if not isinstance(current, SpanContext):
        current = SpanContext(
            trace_id=current.trace_id,
            span_id=current.span_id,
            trace_flags=getattr(current, "trace_flags", "01"),
            is_remote=getattr(current, "is_remote", False),
        )
    target["traceparent"] = "00-{}-{}-{}".format(
        current.trace_id,
        current.span_id,
        current.trace_flags,
    )
    return target


def extract_traceparent(headers):
    if not headers:
        return None
    value = headers.get("traceparent")
    if not value:
        return None
    parts = value.split("-")
    if len(parts) != 4:
        return None
    return {
        "version": parts[0],
        "trace_id": parts[1],
        "span_id": parts[2],
        "trace_flags": parts[3],
    }


def inject_to_carrier(carrier, context=None, field="otel"):
    target = carrier if carrier is not None else {}
    current = context or get_current_span_context()
    if current is None:
        return target
    if not isinstance(current, SpanContext):
        current = SpanContext(
            trace_id=current.trace_id,
            span_id=current.span_id,
            trace_flags=getattr(current, "trace_flags", "01"),
            is_remote=getattr(current, "is_remote", False),
        )
    target[field] = current.to_carrier()
    return target


def extract_from_carrier(carrier, field="otel"):
    if not isinstance(carrier, dict):
        return None
    value = carrier.get(field)
    if not isinstance(value, dict):
        return None
    trace_id = value.get("trace_id")
    span_id = value.get("span_id")
    if not trace_id or not span_id:
        return None
    return SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        trace_flags=value.get("trace_flags", "01"),
        is_remote=True,
    )
