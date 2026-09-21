# OpenTelemetry for MicroPython

This package provides lightweight traces, logs, metrics, context propagation, and HTTP export for MicroPython devices.

It installs as **otel**.

## Role in RPStack

Observability makes service lifecycle failures, sensor latency, operation duration, bridge traffic, and resource pressure visible outside the device. Instrumentation can use the same service identity and operation names declared in RPStack manifests.

The package follows familiar OpenTelemetry concepts while remaining practical on constrained systems.

## Capabilities

- TracerProvider, Tracer, Span, and span context
- LoggerProvider, Logger, LogRecord, and processors
- MeterProvider, Counter, UpDownCounter, Gauge, and Histogram
- simple and queued span/log processors
- metric readers
- HTTP exporters for traces, logs, and metrics
- traceparent injection and extraction
- context attachment
- traced HTTP requests
- global enable and disable controls
- log-level and trace-detail filtering

## Basic tracing

~~~python
from otel import (
    HTTPSpanExporter,
    SimpleSpanProcessor,
    TracerProvider,
    get_tracer,
    set_tracer_provider,
)

provider = TracerProvider(resource={
    "service.name": "lift-controller",
    "device.id": "esp32-01",
})
provider.add_span_processor(
    SimpleSpanProcessor(
        HTTPSpanExporter(
            endpoint="http://collector.local:4318/v1/traces"
        )
    )
)
set_tracer_provider(provider)

tracer = get_tracer("motion")
with tracer.start_as_current_span("move_to") as span:
    span.set_attribute("service.instance", "lift")
    span.set_attribute("motion.target_m", 0.100)
~~~

## Combined OTLP setup

**setup_otlp()** configures the providers and exporters together:

~~~python
from otel import setup_otlp

telemetry = setup_otlp(
    endpoint="http://collector.local:4318",
    service_name="lift-controller",
    async_export=True,
    async_batch_size=16,
    async_queue_size=128,
    async_flush_interval_ms=200,
)
~~~

Queued export moves network work away from latency-sensitive service operations. Spans and log records retain their original timestamps when exported later.

## Context propagation

Use traceparent helpers when an operation crosses a bridge or network boundary:

~~~python
from otel import inject_to_carrier, extract_from_carrier

headers = {}
inject_to_carrier(headers)

remote_context = extract_from_carrier(received_headers)
~~~

This allows a device operation to remain part of an end-to-end trace across REST, ROS-facing gateways, or Lighthouse nodes.

## Metrics and logs

~~~python
from otel import get_logger, get_meter

logger = get_logger("distance-sensor")
logger.info("sensor started", {"service.instance": "lift_tof"})

meter = get_meter("linear-slide")
moves = meter.create_counter("motion.commands")
moves.add(1, {"service.instance": "lift"})
~~~

Use bounded attribute values and conservative metric cardinality on embedded devices.

## Runtime controls

The package exposes controls for:

- enabling and disabling telemetry;
- log level;
- trace detail;
- fallback log handling;
- endpoint probing.

These controls allow a device to reduce overhead without removing instrumentation.

## Installation

~~~python
import mip
mip.install(
    "https://gitlab.com/robot-primitives/Micropython_Modules/"
    "mp_opentelemetry/-/raw/main/package.json"
)
~~~

## RPStack instrumentation guidance

- Use manifest service names as logical service attributes.
- Add the device instance identifier separately.
- Create spans around declared operations and bridge sends.
- Record lifecycle failures and test results as logs.
- Measure operation duration, queue depth, retries, and error counts.
- Avoid exporting synchronously from timing-critical motor loops.
