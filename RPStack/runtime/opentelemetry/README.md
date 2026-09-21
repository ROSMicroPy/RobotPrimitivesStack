# mp_opentelemetry

`mp_opentelemetry` brings traces, logs, and metrics into MicroPython without dragging in a heavyweight observability stack. It is deliberately compact, but it still maps onto familiar OpenTelemetry concepts closely enough to make embedded telemetry useful and portable.

**Project URL**: https://gitlab.com/robot-primitives/Micropython_Modules/mp_opentelemetry

> **Standout:** gives constrained MicroPython systems a practical observability surface instead of treating telemetry as something only full Linux devices deserve.

## Core capabilities

- tracing via `TracerProvider`, `Tracer`, and spans
- logging via `LoggerProvider`, `Logger`, and log processors
- metrics via `MeterProvider`, counters, gauges, and histograms
- `traceparent` propagation helpers
- HTTP export for spans, logs, and metrics using lightweight JSON payloads

## Install with `mip`

```python
import mip
mip.install("https://gitlab.com/robot-primitives/Micropython_Modules/mp_opentelemetry/-/raw/main/package.json")
```

The package installs as `otel` on the device.

## Why it stands out

This project is not trying to be a full OpenTelemetry reimplementation. The value is in picking the smallest useful slice:

- enough API shape to instrument real applications
- enough export functionality to integrate with collectors or custom endpoints
- small enough assumptions to stay realistic on MicroPython boards

## Quick start

```python
from otel import TracerProvider, SimpleSpanProcessor, HTTPSpanExporter, set_tracer_provider, get_tracer

provider = TracerProvider(resource={"service.name": "sensor-node"})
provider.add_span_processor(SimpleSpanProcessor(HTTPSpanExporter(endpoint="http://collector.local:4318/v1/traces")))
set_tracer_provider(provider)

tracer = get_tracer("sensor-loop")
with tracer.start_as_current_span("sample") as span:
    span.set_attribute("device.id", "esp32-01")
```

For a fuller example, see the repository example code.

## Async export

For latency-sensitive code paths, `setup_otlp()` can queue spans and log records and export them from a background thread:

```python
from otel import setup_otlp

setup = setup_otlp(
    endpoint="http://collector.local:4318",
    service_name="sensor-node",
    async_export=True,
    async_batch_size=16,
    async_queue_size=128,
    async_flush_interval_ms=200,
)
```

Queued export preserves the original timestamps already stored on each `Span` and `LogRecord`. Export time does not overwrite record creation or span end time.
