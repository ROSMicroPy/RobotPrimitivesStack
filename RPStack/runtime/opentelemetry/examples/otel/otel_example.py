
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
import os
import sys
import time
import ntptime
import wifi

OTEL_EXPORTER_OTLP_ENDPOINT ="http://192.168.8.192:4318"

from rpstack.opentelemetry import (
    get_logger,
    get_meter,
    get_tracer,
    setup_otlp,
    traced_request,
)


def setup_tracing():
    setup = setup_otlp(
        endpoint=OTEL_EXPORTER_OTLP_ENDPOINT,
        service_name="mpy-demo",
        timeout_s=2,
    )
    return setup["metric_reader"]


def main():

    try:
        print("Local time before synchronization：%s" %str(time.localtime()))
        ntptime.settime()
        print("Local time after synchronization：%s" %str(time.localtime()))
    except:
        print("Error setting ntp time")

    metric_reader = setup_tracing()
    tracer = get_tracer("app")
    logger = get_logger("app")
    meter = get_meter("app")
    run_counter = meter.create_counter("app.runs", unit="1")
    duration_ms = meter.create_histogram("app.work.duration", unit="ms")

    with tracer.start_as_current_span("work") as span:
        span.set_attribute("device.id", "esp32-01")
        span.add_event("starting")
        span.set_status("OK")
        logger.info("work started", {"device.id": "esp32-01"})
        run_counter.add(1, {"device.id": "esp32-01"})
        duration_ms.record(3.2, {"device.id": "esp32-01"})

    metric_reader.collect()

    # Optional outgoing HTTP call with span + traceparent injection.
    # response = traced_request(tracer, "GET", "http://httpbin.org/get")
    # response.close()


if __name__ == "__main__":
    main()
