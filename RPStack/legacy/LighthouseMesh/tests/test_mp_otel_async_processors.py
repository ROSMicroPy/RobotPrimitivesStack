import importlib.util
import pathlib
import sys
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
OTEL_ROOT = ROOT.parent / "MicropythonModules" / "mp_opentelemetry" / "src"


def _load_package(name, init_path, package_root):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name,
        str(init_path),
        submodule_search_locations=[str(package_root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _FakeExporter:
    def __init__(self, status=200):
        self.calls = []
        self.status = status

    def export(self, items, resource=None):
        self.calls.append((list(items), resource))
        return self.status

    def shutdown(self):
        return True


class AsyncProcessorTimestampTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _load_package("otel", OTEL_ROOT / "__init__.py", OTEL_ROOT)

    def test_queued_span_processor_preserves_span_end_time(self):
        from otel.api import set_tracer_provider
        from otel.processor import QueuedSpanProcessor
        from otel.trace import TracerProvider

        exporter = _FakeExporter()
        provider = TracerProvider(resource={"service.name": "async-span-test"})
        processor = QueuedSpanProcessor(exporter, auto_start=False)
        provider.add_span_processor(processor)
        set_tracer_provider(provider)

        tracer = provider.get_tracer("span-test")
        with tracer.start_span("queued-span") as span:
            span.set_attribute("device.id", "node2")
        recorded_end = span.end_time_unix_nano

        time.sleep(0.01)
        processor.flush()

        self.assertEqual(1, len(exporter.calls))
        exported_span = exporter.calls[0][0][0]
        self.assertEqual(recorded_end, exported_span.end_time_unix_nano)

    def test_queued_log_processor_preserves_log_timestamp(self):
        from otel.api import enable_telemetry, set_log_level, set_logger_provider
        from otel.logging import LoggerProvider
        from otel.processor import QueuedLogProcessor

        enable_telemetry()
        set_log_level("DEBUG")
        exporter = _FakeExporter()
        provider = LoggerProvider(resource={"service.name": "async-log-test"})
        processor = QueuedLogProcessor(exporter, auto_start=False)
        provider.add_log_processor(processor)
        set_logger_provider(provider)

        logger = provider.get_logger("log-test")
        record = logger.info("queued log", attributes={"path": "hot"})
        recorded_timestamp = record.timestamp_unix_nano

        time.sleep(0.01)
        processor.flush()

        self.assertEqual(1, len(exporter.calls))
        exported_record = exporter.calls[0][0][0]
        self.assertEqual(recorded_timestamp, exported_record.timestamp_unix_nano)

    def test_essential_trace_mode_filters_diagnostic_spans(self):
        from otel.api import set_trace_detail_mode, set_tracer_provider
        from otel.trace import TracerProvider

        provider = TracerProvider(resource={"service.name": "trace-filter-test"})
        set_tracer_provider(provider)
        tracer = provider.get_tracer("filter-test")

        set_trace_detail_mode("essential", essential_prefixes=("node2.",))
        with tracer.start_span("node2.on_message"):
            pass
        with tracer.start_span("dnet.signalling.mesh.recv_raw"):
            pass

        names = [span["name"] for span in provider.snapshot()]
        self.assertIn("node2.on_message", names)
        self.assertNotIn("dnet.signalling.mesh.recv_raw", names)

        set_trace_detail_mode("diagnostic", essential_prefixes=("node2.",))

    def test_logger_provider_filters_below_min_severity(self):
        from otel.api import enable_telemetry, set_log_level, set_logger_provider
        from otel.logging import LoggerProvider
        from otel.processor import SimpleLogProcessor

        enable_telemetry()
        set_log_level("ERROR")
        exporter = _FakeExporter()
        provider = LoggerProvider(resource={"service.name": "log-level-test"}, min_severity="ERROR")
        provider.add_log_processor(SimpleLogProcessor(exporter))
        set_logger_provider(provider)

        logger = provider.get_logger("log-level-test")
        logger.info("ignored")
        logger.error("kept")

        self.assertEqual(1, len(exporter.calls))
        self.assertEqual("kept", exporter.calls[0][0][0].body)

    def test_queued_log_processor_falls_back_on_export_failure(self):
        from otel.api import enable_telemetry, set_log_fallback_handler, set_log_level, set_logger_provider
        from otel.logging import LoggerProvider
        from otel.processor import QueuedLogProcessor

        enable_telemetry()
        set_log_level("ERROR")
        exporter = _FakeExporter(status=0)
        fallback_records = []

        def fallback(record, resource=None):
            fallback_records.append((record.body, resource))

        provider = LoggerProvider(
            resource={"service.name": "async-log-fallback-test"},
            min_severity="ERROR",
            fallback_handler=fallback,
        )
        processor = QueuedLogProcessor(exporter, auto_start=False, failure_callback=fallback)
        provider.add_log_processor(processor)
        set_log_fallback_handler(fallback)
        set_logger_provider(provider)

        logger = provider.get_logger("fallback-test")
        logger.error("collector down")
        processor.flush()

        self.assertEqual(1, len(exporter.calls))
        self.assertEqual([("collector down", {"service.name": "async-log-fallback-test"})], fallback_records)

    def test_forced_info_log_bypasses_error_level_filter(self):
        from otel.api import enable_telemetry, set_log_level, set_logger_provider
        from otel.logging import LoggerProvider
        from otel.processor import SimpleLogProcessor

        enable_telemetry()
        set_log_level("ERROR")
        exporter = _FakeExporter()
        provider = LoggerProvider(resource={"service.name": "forced-log-test"}, min_severity="ERROR")
        provider.add_log_processor(SimpleLogProcessor(exporter))
        set_logger_provider(provider)

        logger = provider.get_logger("forced-log-test")
        logger.info("forced info", force=True)

        self.assertEqual(1, len(exporter.calls))
        self.assertEqual("forced info", exporter.calls[0][0][0].body)

    def test_setup_otlp_retries_probe_before_disabling(self):
        import otel.api as api

        calls = []
        original_probe = api.probe_endpoint
        try:
            def fake_probe(endpoint, timeout_s=2):
                calls.append((endpoint, timeout_s))
                return len(calls) >= 3

            api.probe_endpoint = fake_probe
            result = api.setup_otlp(
                endpoint="http://collector:4318",
                service_name="retry-test",
                probe_max_attempts=3,
                probe_retry_delay_s=0,
            )
        finally:
            api.probe_endpoint = original_probe

        self.assertTrue(result["enabled"])
        self.assertEqual(3, len(calls))


if __name__ == "__main__":
    unittest.main()
