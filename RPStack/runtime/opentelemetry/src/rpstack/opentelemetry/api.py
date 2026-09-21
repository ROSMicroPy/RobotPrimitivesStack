try:
    import utime as _time
except ImportError:
    import time as _time

# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
from .exporter import probe_endpoint
from .logging import LoggerProvider, NoOpLoggerProvider
from .metric import MeterProvider, NoOpMeterProvider
from .processor import NoOpMetricReader
from .trace import TracerProvider, NoOpTracerProvider

_TRACER_PROVIDER = TracerProvider()
_LOGGER_PROVIDER = LoggerProvider()
_METER_PROVIDER = MeterProvider()
_NOOP_TRACER_PROVIDER = NoOpTracerProvider()
_NOOP_LOGGER_PROVIDER = NoOpLoggerProvider()
_NOOP_METER_PROVIDER = NoOpMeterProvider()
_TELEMETRY_ENABLED = True
_TRACE_DETAIL_MODE = 'diagnostic'
_ESSENTIAL_SPAN_PREFIXES = ()
_LOG_LEVEL = 'DEBUG'
_LOG_FALLBACK_HANDLER = None


def _normalize_otlp_endpoint(endpoint, signal_path):
    endpoint = str(endpoint or '').rstrip('/')
    signal_path = str(signal_path or '')
    if not signal_path.startswith('/'):
        signal_path = '/{}'.format(signal_path)
    if endpoint.endswith(signal_path):
        endpoint = endpoint[:-len(signal_path)]
    return '{}{}'.format(endpoint, signal_path)


def _sleep_seconds(seconds):
    seconds = max(0, int(seconds or 0))
    if hasattr(_time, "sleep"):
        _time.sleep(seconds)
        return


def _probe_endpoint_with_retry(endpoint, timeout_s=2, max_attempts=1, retry_delay_s=0):
    attempts = max(1, int(max_attempts or 1))
    delay_s = max(0, int(retry_delay_s or 0))
    for attempt in range(1, attempts + 1):
        if probe_endpoint(endpoint, timeout_s=timeout_s):
            return True
        if attempt < attempts and delay_s > 0:
            _sleep_seconds(delay_s)
    return False


def _set_enabled(enabled):
    global _TELEMETRY_ENABLED
    _TELEMETRY_ENABLED = bool(enabled)


def enable_telemetry():
    _set_enabled(True)
    return True


def disable_telemetry(message=None):
    was_enabled = is_telemetry_enabled()
    _set_enabled(False)
    if message and was_enabled:
        print(message)
    return True


def is_telemetry_enabled():
    return bool(_TELEMETRY_ENABLED)


def set_trace_detail_mode(mode='diagnostic', essential_prefixes=None):
    global _TRACE_DETAIL_MODE, _ESSENTIAL_SPAN_PREFIXES
    requested = str(mode or 'diagnostic').strip().lower()
    if requested not in ('diagnostic', 'essential'):
        requested = 'diagnostic'
    _TRACE_DETAIL_MODE = requested
    if essential_prefixes is None:
        return True
    normalized = []
    for prefix in essential_prefixes:
        text = str(prefix or '').strip()
        if text:
            normalized.append(text)
    _ESSENTIAL_SPAN_PREFIXES = tuple(normalized)
    return True


def get_trace_detail_mode():
    return _TRACE_DETAIL_MODE


def should_emit_span(name):
    if not is_telemetry_enabled():
        return False
    if _TRACE_DETAIL_MODE != 'essential':
        return True
    if not _ESSENTIAL_SPAN_PREFIXES:
        return True
    span_name = str(name or '')
    for prefix in _ESSENTIAL_SPAN_PREFIXES:
        if span_name.startswith(prefix):
            return True
    return False


def set_tracer_provider(provider):
    global _TRACER_PROVIDER
    _TRACER_PROVIDER = provider


def get_tracer_provider():
    if not is_telemetry_enabled():
        return _NOOP_TRACER_PROVIDER
    return _TRACER_PROVIDER


def get_tracer(name):
    return get_tracer_provider().get_tracer(name)


def set_logger_provider(provider):
    global _LOGGER_PROVIDER
    _LOGGER_PROVIDER = provider
    if hasattr(provider, 'set_min_severity'):
        provider.set_min_severity(_LOG_LEVEL)
    if _LOG_FALLBACK_HANDLER is not None and hasattr(provider, 'set_fallback_handler'):
        provider.set_fallback_handler(_LOG_FALLBACK_HANDLER)


def get_logger_provider():
    if not is_telemetry_enabled():
        return _NOOP_LOGGER_PROVIDER
    return _LOGGER_PROVIDER


def get_logger(name):
    return get_logger_provider().get_logger(name)


def set_log_level(level='DEBUG'):
    global _LOG_LEVEL
    candidate = str(level or 'DEBUG').strip().upper()
    if candidate == 'WARNING':
        candidate = 'WARN'
    if candidate not in ('DEBUG', 'INFO', 'WARN', 'ERROR'):
        candidate = 'DEBUG'
    _LOG_LEVEL = candidate
    provider = _LOGGER_PROVIDER
    if hasattr(provider, 'set_min_severity'):
        provider.set_min_severity(candidate)
    return candidate


def get_log_level():
    return _LOG_LEVEL


def set_log_fallback_handler(handler=None):
    global _LOG_FALLBACK_HANDLER
    _LOG_FALLBACK_HANDLER = handler
    provider = _LOGGER_PROVIDER
    if hasattr(provider, 'set_fallback_handler'):
        provider.set_fallback_handler(handler)
    return True


def set_meter_provider(provider):
    global _METER_PROVIDER
    _METER_PROVIDER = provider


def get_meter_provider():
    if not is_telemetry_enabled():
        return _NOOP_METER_PROVIDER
    return _METER_PROVIDER


def get_meter(name):
    return get_meter_provider().get_meter(name)


def setup_otlp(
    endpoint,
    service_name,
    timeout_s=2,
    trace_path='/v1/traces',
    metric_path='/v1/metrics',
    log_path='/v1/logs',
    resource=None,
    async_export=False,
    async_batch_size=16,
    async_queue_size=128,
    async_flush_interval_ms=200,
    log_level=None,
    log_fallback_handler=None,
    probe_max_attempts=1,
    probe_retry_delay_s=0,
):
    global _LOG_FALLBACK_HANDLER, _LOG_LEVEL
    from .exporter import HTTPLogExporter, HTTPMetricExporter, HTTPSpanExporter
    from .processor import (
        MetricReader,
        QueuedLogProcessor,
        QueuedSpanProcessor,
        SimpleLogProcessor,
        SimpleSpanProcessor,
    )

    resource_data = {'service.name': str(service_name)}
    for key, value in (resource or {}).items():
        resource_data[str(key)] = value

    base_endpoint = str(endpoint or '').rstrip('/')
    if not _probe_endpoint_with_retry(
        base_endpoint,
        timeout_s=timeout_s,
        max_attempts=probe_max_attempts,
        retry_delay_s=probe_retry_delay_s,
    ):
        disable_telemetry('otel endpoint is down')
        return {
            'tracer_provider': get_tracer_provider(),
            'logger_provider': get_logger_provider(),
            'meter_provider': get_meter_provider(),
            'metric_reader': NoOpMetricReader(),
            'resource': resource_data,
            'enabled': False,
        }

    enable_telemetry()

    trace_exporter = HTTPSpanExporter(
        endpoint=_normalize_otlp_endpoint(base_endpoint, trace_path),
        headers={'Content-Type': 'application/json'},
        timeout_s=timeout_s,
    )
    tracer_provider = TracerProvider(resource=resource_data)
    span_processor = None
    if async_export:
        span_processor = QueuedSpanProcessor(
            trace_exporter,
            batch_size=async_batch_size,
            queue_size=async_queue_size,
            flush_interval_ms=async_flush_interval_ms,
            auto_start=False,
        )
        if not span_processor.start_worker():
            span_processor = SimpleSpanProcessor(trace_exporter, batch_size=async_batch_size)
    else:
        span_processor = SimpleSpanProcessor(trace_exporter, batch_size=async_batch_size)
    tracer_provider.add_span_processor(span_processor)
    set_tracer_provider(tracer_provider)

    log_exporter = HTTPLogExporter(
        endpoint=_normalize_otlp_endpoint(base_endpoint, log_path),
        headers={'Content-Type': 'application/json'},
        timeout_s=timeout_s,
    )
    if log_level is None:
        log_level = _LOG_LEVEL
    if log_fallback_handler is None:
        log_fallback_handler = _LOG_FALLBACK_HANDLER
    logger_provider = LoggerProvider(
        resource=resource_data,
        min_severity=log_level,
        fallback_handler=log_fallback_handler,
    )
    _LOG_LEVEL = logger_provider.get_min_severity()
    if log_fallback_handler is not None:
        _LOG_FALLBACK_HANDLER = log_fallback_handler
    log_processor = None
    if async_export:
        log_processor = QueuedLogProcessor(
            log_exporter,
            batch_size=async_batch_size,
            queue_size=async_queue_size,
            flush_interval_ms=async_flush_interval_ms,
            auto_start=False,
            failure_callback=log_fallback_handler,
        )
        if not log_processor.start_worker():
            log_processor = SimpleLogProcessor(log_exporter, failure_callback=log_fallback_handler)
    else:
        log_processor = SimpleLogProcessor(log_exporter, failure_callback=log_fallback_handler)
    logger_provider.add_log_processor(log_processor)
    set_logger_provider(logger_provider)

    metric_exporter = HTTPMetricExporter(
        endpoint=_normalize_otlp_endpoint(base_endpoint, metric_path),
        headers={'Content-Type': 'application/json'},
        timeout_s=timeout_s,
    )
    meter_provider = MeterProvider(resource=resource_data)
    metric_reader = MetricReader(metric_exporter)
    meter_provider.add_metric_reader(metric_reader)
    set_meter_provider(meter_provider)
    return {
        'tracer_provider': tracer_provider,
        'logger_provider': logger_provider,
        'meter_provider': meter_provider,
        'metric_reader': metric_reader,
        'span_processor': span_processor,
        'log_processor': log_processor,
        'resource': resource_data,
        'enabled': True,
        'async_export': bool(async_export),
    }
