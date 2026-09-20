# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
import os

try:
    import ujson as json
except ImportError:
    import json

from .util import now_unix_nanos


_STATUS_CODE_MAP = {'UNSET': 0, 'OK': 1, 'ERROR': 2}
_SEVERITY_NUMBER_MAP = {
    'TRACE': 1,
    'DEBUG': 5,
    'INFO': 9,
    'WARN': 13,
    'WARNING': 13,
    'ERROR': 17,
    'FATAL': 21,
}
_EXPORT_DEBUG_ENABLED = False
_EXPORT_DEBUG_LOG_PATH = '/otel_logs.txt'


def configure_debug(enabled=False, log_path=None):
    global _EXPORT_DEBUG_ENABLED, _EXPORT_DEBUG_LOG_PATH
    _EXPORT_DEBUG_ENABLED = bool(enabled)
    if log_path:
        _EXPORT_DEBUG_LOG_PATH = str(log_path)


def _getenv(name):
    getenv = getattr(os, 'getenv', None)
    if callable(getenv):
        return getenv(name)
    if hasattr(os, 'environ'):
        try:
            return os.environ.get(name)
        except Exception:
            return None
    return None


def _is_debug_enabled():
    if _EXPORT_DEBUG_ENABLED:
        return True
    debug_value = _getenv('OTEL_EXPORT_DEBUG')
    return debug_value in ('1', 'true', 'TRUE', 'yes', 'YES')


def _telemetry_enabled():
    try:
        from .api import is_telemetry_enabled

        return is_telemetry_enabled()
    except Exception:
        return True


def _disable_telemetry(message=None):
    try:
        from .api import disable_telemetry

        disable_telemetry(message=message)
    except Exception:
        if message:
            print(message)


def _debug_log(message):
    if not _is_debug_enabled():
        return
    try:
        with open(_EXPORT_DEBUG_LOG_PATH, 'a') as handle:
            handle.write('{}\n'.format(str(message)))
    except Exception:
        pass


def _is_timeout_error(exc):
    text = str(exc or '')
    if 'ETIMEDOUT' in text or 'ETIMEOUT' in text or 'timed out' in text or 'timeout' in text.lower():
        return True
    args = getattr(exc, 'args', ()) or ()
    for value in args:
        if value in ('ETIMEDOUT', 'ETIMEOUT', 110, 116):
            return True
        if isinstance(value, str) and (('ETIMEDOUT' in value) or ('ETIMEOUT' in value) or ('timeout' in value.lower())):
            return True
    errno = getattr(exc, 'errno', None)
    if errno in (110, 116):
        return True
    return False


def _debug_export_error(exc):
    if _is_timeout_error(exc):
        return
    _debug_log('otel export failed: {}'.format(exc))
    if _is_debug_enabled() and _telemetry_enabled():
        try:
            import sys

            sys.stderr.write('otel export failed: {}\n'.format(exc))
        except Exception:
            pass


def _response_status(response):
    if response is None:
        return 0
    return getattr(response, 'status_code', getattr(response, 'code', 0)) or 0


def _close_response(response):
    if response is not None and hasattr(response, 'close'):
        try:
            response.close()
        except Exception:
            pass


def probe_endpoint(endpoint, timeout_s=2):
    if not endpoint:
        return False

    try:
        import urequests as requests  # type: ignore

        response = None
        try:
            response = requests.get(endpoint, timeout=timeout_s)
            return bool(_response_status(response))
        except Exception as exc:
            if _is_timeout_error(exc):
                return False
            status = _response_status(getattr(exc, 'response', None))
            return bool(status)
        finally:
            _close_response(response)
    except ImportError:
        from urllib import error, request

        try:
            with request.urlopen(endpoint, timeout=timeout_s) as response:
                return bool(getattr(response, 'getcode', lambda: 0)())
        except error.HTTPError as exc:
            return bool(getattr(exc, 'code', 0))
        except Exception as exc:
            if _is_timeout_error(exc):
                return False
            return False


def _post_json(endpoint, payload, headers=None, timeout_s=2, signal_name='otlp'):
    if not _telemetry_enabled():
        return 0

    body = json.dumps(payload)
    _debug_log(
        'otel export start signal={} endpoint={} bytes={} timeout_s={}'.format(
            signal_name,
            endpoint,
            len(body),
            timeout_s,
        )
    )

    try:
        import urequests as requests  # type: ignore

        response = None
        try:
            response = requests.post(
                endpoint,
                data=body,
                headers=headers or {'Content-Type': 'application/json'},
                timeout=timeout_s,
            )
            status = _response_status(response)
            _debug_log(
                'otel export done signal={} endpoint={} status={}'.format(
                    signal_name,
                    endpoint,
                    status,
                )
            )
            return status
        except Exception as exc:
            if _is_timeout_error(exc):
                _disable_telemetry('otel endpoint is down')
                return 0
            _debug_export_error(exc)
            return 0
        finally:
            _close_response(response)
    except ImportError:
        from urllib import error, request

        try:
            req = request.Request(
                endpoint,
                data=body.encode('utf-8'),
                headers=headers or {'Content-Type': 'application/json'},
                method='POST',
            )
            with request.urlopen(req, timeout=timeout_s) as response:
                status = response.getcode()
                _debug_log(
                    'otel export done signal={} endpoint={} status={}'.format(
                        signal_name,
                        endpoint,
                        status,
                    )
                )
                return status
        except error.HTTPError as exc:
            status = getattr(exc, 'code', 0) or 0
            _debug_log(
                'otel export done signal={} endpoint={} status={}'.format(
                    signal_name,
                    endpoint,
                    status,
                )
            )
            return status
        except Exception as exc:
            _disable_telemetry('otel endpoint is down')
            return 0


def _as_otel_value(value):
    if value is None:
        return {'stringValue': ''}
    if isinstance(value, bool):
        return {'boolValue': value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {'intValue': str(value)}
    if isinstance(value, float):
        return {'doubleValue': value}
    if isinstance(value, dict):
        return {
            'kvlistValue': {
                'values': [_key_value_item(key, item) for key, item in value.items()]
            }
        }
    if isinstance(value, (list, tuple)):
        return {'arrayValue': {'values': [_as_otel_value(item) for item in value]}}
    return {'stringValue': str(value)}


def _key_value_item(key, value):
    return {'key': str(key), 'value': _as_otel_value(value)}


def _attributes_kv(attributes):
    return [_key_value_item(key, value) for key, value in (attributes or {}).items()]


def _resource_data(resource):
    return {'attributes': _attributes_kv(resource)}


def _append_scope_item(scope_map, scope_name, payload_key, items):
    scope_entry = scope_map.get(scope_name)
    if scope_entry is None:
        scope_entry = {'scope': {'name': scope_name}, payload_key: []}
        scope_map[scope_name] = scope_entry
    scope_entry[payload_key].extend(items)


def _trace_payload(spans, resource=None):
    scope_spans = {}
    for span in spans:
        otel_span = {
            'traceId': span.trace_id,
            'spanId': span.span_id,
            'name': span.name,
            'kind': 1,
            'startTimeUnixNano': str(span.start_time_unix_nano),
            'endTimeUnixNano': str(span.end_time_unix_nano or now_unix_nanos()),
            'attributes': _attributes_kv(span.attributes),
            'events': [],
            'status': {
                'code': _STATUS_CODE_MAP.get(span.status_code, 0),
                'message': span.status_message,
            },
        }
        if span.parent_span_id:
            otel_span['parentSpanId'] = span.parent_span_id
        for event in span.events:
            otel_span['events'].append(
                {
                    'name': event.get('name', ''),
                    'timeUnixNano': str(event.get('time_unix_nano', now_unix_nanos())),
                    'attributes': _attributes_kv(event.get('attributes', {})),
                }
            )
        scope_name = getattr(getattr(span, '_tracer', None), 'name', 'mp_opentelemetry')
        _append_scope_item(scope_spans, scope_name, 'spans', [otel_span])

    return {
        'resourceSpans': [
            {
                'resource': _resource_data(resource or {}),
                'scopeSpans': list(scope_spans.values()),
            }
        ]
    }


def _log_payload(records, resource=None):
    scope_logs = {}
    for record in records:
        otel_record = {
            'timeUnixNano': str(record.timestamp_unix_nano),
            'observedTimeUnixNano': str(record.timestamp_unix_nano),
            'severityNumber': _SEVERITY_NUMBER_MAP.get(record.severity_text.upper(), 0),
            'severityText': record.severity_text,
            'body': _as_otel_value(record.body),
            'attributes': _attributes_kv(record.attributes),
        }
        if record.trace_id:
            otel_record['traceId'] = record.trace_id
        if record.span_id:
            otel_record['spanId'] = record.span_id
        _append_scope_item(scope_logs, record.logger_name, 'logRecords', [otel_record])

    return {
        'resourceLogs': [
            {
                'resource': _resource_data(resource or {}),
                'scopeLogs': list(scope_logs.values()),
            }
        ]
    }


def _number_data_point(point, current_time_unix_nano):
    data_point = {
        'attributes': _attributes_kv(point.get('attributes', {})),
        'timeUnixNano': str(current_time_unix_nano),
    }
    start_time_unix_nano = point.get('start_time_unix_nano')
    if start_time_unix_nano is not None:
        data_point['startTimeUnixNano'] = str(start_time_unix_nano)

    value = point.get('value', 0)
    if isinstance(value, int) and not isinstance(value, bool):
        data_point['asInt'] = str(value)
    else:
        data_point['asDouble'] = float(value)
    return data_point


def _metric_payload(metrics, resource=None):
    current_time_unix_nano = now_unix_nanos()
    scope_metrics = {}
    for metric in metrics:
        entry = {
            'name': metric.get('name', ''),
            'description': metric.get('description', ''),
            'unit': metric.get('unit', ''),
        }
        kind = metric.get('kind')
        points = metric.get('points', [])
        if kind == 'counter':
            entry['sum'] = {
                'aggregationTemporality': 2,
                'isMonotonic': True,
                'dataPoints': [
                    _number_data_point(point, current_time_unix_nano) for point in points
                ],
            }
        elif kind == 'up_down_counter':
            entry['sum'] = {
                'aggregationTemporality': 2,
                'isMonotonic': False,
                'dataPoints': [
                    _number_data_point(point, current_time_unix_nano) for point in points
                ],
            }
        elif kind == 'gauge':
            entry['gauge'] = {
                'dataPoints': [
                    _number_data_point(point, current_time_unix_nano) for point in points
                ]
            }
        elif kind == 'histogram':
            entry['histogram'] = {
                'aggregationTemporality': 2,
                'dataPoints': [
                    {
                        'attributes': _attributes_kv(point.get('attributes', {})),
                        'startTimeUnixNano': str(
                            point.get('start_time_unix_nano', current_time_unix_nano)
                        ),
                        'timeUnixNano': str(current_time_unix_nano),
                        'count': str(point.get('count', 0)),
                        'sum': float(point.get('sum', 0)),
                        'bucketCounts': [str(point.get('count', 0))],
                        'explicitBounds': [],
                        'min': float(point.get('min', 0) or 0),
                        'max': float(point.get('max', 0) or 0),
                    }
                    for point in points
                ]
            }
        else:
            continue
        _append_scope_item(
            scope_metrics,
            metric.get('meter_name', 'mp_opentelemetry'),
            'metrics',
            [entry],
        )

    return {
        'resourceMetrics': [
            {
                'resource': _resource_data(resource or {}),
                'scopeMetrics': list(scope_metrics.values()),
            }
        ]
    }


class _BaseHTTPExporter:
    def __init__(self, endpoint, headers=None, timeout_s=2):
        self.endpoint = endpoint
        self.headers = headers or {'Content-Type': 'application/json'}
        self.timeout_s = timeout_s

    def shutdown(self):
        return


class HTTPSpanExporter(_BaseHTTPExporter):
    def export(self, spans, resource=None):
        payload = _trace_payload(spans, resource=resource)
        return _post_json(self.endpoint, payload, self.headers, self.timeout_s, signal_name='traces')


class HTTPLogExporter(_BaseHTTPExporter):
    def export(self, records, resource=None):
        payload = _log_payload(records, resource=resource)
        return _post_json(self.endpoint, payload, self.headers, self.timeout_s, signal_name='logs')


class HTTPMetricExporter(_BaseHTTPExporter):
    def export(self, metrics, resource=None):
        payload = _metric_payload(metrics, resource=resource)
        return _post_json(self.endpoint, payload, self.headers, self.timeout_s, signal_name='metrics')
