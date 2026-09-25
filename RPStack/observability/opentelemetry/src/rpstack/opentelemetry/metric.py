# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
from .util import now_unix_nanos


# Consult the shared enable switch, defaulting to enabled if the API is unavailable.
def _telemetry_enabled():
    try:
        from .api import is_telemetry_enabled

        return is_telemetry_enabled()
    except Exception:
        return True


class _MetricPointSet:
    # Prepare attribute-keyed metric storage and its initial timestamp.
    def __init__(self):
        self._points = {}
        self.start_time_unix_nano = now_unix_nanos()

    # Normalize metric attribute names to strings before point grouping.
    def _normalize_attributes(self, attributes):
        normalized = {}
        for key, value in (attributes or {}).items():
            normalized[str(key)] = value
        return normalized

    # Create a stable sorted attribute key and its normalized attribute mapping.
    def _point_key(self, attributes):
        normalized = self._normalize_attributes(attributes)
        items = list(normalized.items())
        items.sort()
        return tuple(items), normalized

    # Return shallow copies of the accumulated metric points.
    def snapshot(self):
        points = []
        for key in self._points:
            point = self._points[key]
            points.append(point.copy())
        return points


class Counter(_MetricPointSet):
    kind = 'counter'

    # Describe a counter instrument and initialize its attribute-keyed point storage.
    def __init__(self, meter_name, name, unit='', description=''):
        super().__init__()
        self.meter_name = meter_name
        self.name = name
        self.unit = unit
        self.description = description

    # Accumulate an amount into the point identified by its attributes when telemetry is
    # enabled.
    def add(self, amount, attributes=None):
        if not _telemetry_enabled():
            return True
        point_key, normalized = self._point_key(attributes)
        point = self._points.get(point_key)
        if point is None:
            point = {
                'attributes': normalized,
                'value': 0,
                'start_time_unix_nano': now_unix_nanos(),
            }
            self._points[point_key] = point
        point['value'] += amount
        return True

    # Package counter metadata and accumulated points for export.
    def collect(self):
        return {
            'meter_name': self.meter_name,
            'name': self.name,
            'description': self.description,
            'unit': self.unit,
            'kind': self.kind,
            'points': self.snapshot(),
        }


class UpDownCounter(Counter):
    kind = 'up_down_counter'


class Gauge(_MetricPointSet):
    kind = 'gauge'

    # Describe a gauge instrument and initialize its attribute-keyed point storage.
    def __init__(self, meter_name, name, unit='', description=''):
        super().__init__()
        self.meter_name = meter_name
        self.name = name
        self.unit = unit
        self.description = description

    # Replace an attribute group's latest value while preserving its first observation time.
    def set(self, value, attributes=None):
        if not _telemetry_enabled():
            return True
        point_key, normalized = self._point_key(attributes)
        existing = self._points.get(point_key)
        start_time_unix_nano = now_unix_nanos()
        if existing is not None:
            start_time_unix_nano = existing.get('start_time_unix_nano', start_time_unix_nano)
        self._points[point_key] = {
            'attributes': normalized,
            'value': value,
            'start_time_unix_nano': start_time_unix_nano,
        }
        return True

    # Package gauge metadata and current values for export.
    def collect(self):
        return {
            'meter_name': self.meter_name,
            'name': self.name,
            'description': self.description,
            'unit': self.unit,
            'kind': self.kind,
            'points': self.snapshot(),
        }


class Histogram(_MetricPointSet):
    kind = 'histogram'

    # Describe a histogram instrument and prepare per-attribute aggregate storage.
    def __init__(self, meter_name, name, unit='', description=''):
        super().__init__()
        self.meter_name = meter_name
        self.name = name
        self.unit = unit
        self.description = description

    # Update count, sum, minimum, and maximum for the sample's attribute group.
    def record(self, value, attributes=None):
        if not _telemetry_enabled():
            return True
        point_key, normalized = self._point_key(attributes)
        point = self._points.get(point_key)
        if point is None:
            point = {
                'attributes': normalized,
                'count': 0,
                'sum': 0,
                'min': None,
                'max': None,
                'start_time_unix_nano': now_unix_nanos(),
            }
            self._points[point_key] = point
        point['count'] += 1
        point['sum'] += value
        point['min'] = value if point['min'] is None else min(point['min'], value)
        point['max'] = value if point['max'] is None else max(point['max'], value)
        return True

    # Package histogram metadata and aggregate points for export.
    def collect(self):
        return {
            'meter_name': self.meter_name,
            'name': self.name,
            'description': self.description,
            'unit': self.unit,
            'kind': self.kind,
            'points': self.snapshot(),
        }


class NoOpCounter:
    kind = 'counter'

    # Retain instrument metadata while omitting metric point storage.
    def __init__(self, meter_name='', name='', unit='', description=''):
        self.meter_name = meter_name
        self.name = name
        self.unit = unit
        self.description = description

    # Accept a counter update without accumulating a metric point.
    def add(self, amount, attributes=None):
        return True

    # Return instrument metadata with no recorded points.
    def collect(self):
        return {
            'meter_name': self.meter_name,
            'name': self.name,
            'description': self.description,
            'unit': self.unit,
            'kind': self.kind,
            'points': [],
        }


class NoOpUpDownCounter(NoOpCounter):
    kind = 'up_down_counter'


class NoOpGauge(NoOpCounter):
    kind = 'gauge'

    # Accept a gauge update without retaining a metric point.
    def set(self, value, attributes=None):
        return True


class NoOpHistogram(NoOpCounter):
    kind = 'histogram'

    # Accept a histogram sample without accumulating observations.
    def record(self, value, attributes=None):
        return True


class Meter:
    # Bind an instrumentation scope to the provider that owns its metric instruments.
    def __init__(self, provider, name):
        self._provider = provider
        self.name = name

    # Register a counter, or return an inert instrument when telemetry is disabled.
    def create_counter(self, name, unit='', description=''):
        if not _telemetry_enabled():
            return NoOpCounter(self.name, name, unit=unit, description=description)
        return self._provider._register(
            Counter(self.name, name, unit=unit, description=description)
        )

    # Register a signed counter, or return an inert instrument when telemetry is disabled.
    def create_up_down_counter(self, name, unit='', description=''):
        if not _telemetry_enabled():
            return NoOpUpDownCounter(self.name, name, unit=unit, description=description)
        return self._provider._register(
            UpDownCounter(self.name, name, unit=unit, description=description)
        )

    # Register a gauge, or return an inert instrument when telemetry is disabled.
    def create_gauge(self, name, unit='', description=''):
        if not _telemetry_enabled():
            return NoOpGauge(self.name, name, unit=unit, description=description)
        return self._provider._register(
            Gauge(self.name, name, unit=unit, description=description)
        )

    # Register a histogram, or return an inert instrument when telemetry is disabled.
    def create_histogram(self, name, unit='', description=''):
        if not _telemetry_enabled():
            return NoOpHistogram(self.name, name, unit=unit, description=description)
        return self._provider._register(
            Histogram(self.name, name, unit=unit, description=description)
        )


class NoOpMeter:
    # Retain the instrumentation name for this non-recording telemetry interface.
    def __init__(self, name):
        self.name = name

    # Create a non-recording counter with the requested metadata.
    def create_counter(self, name, unit='', description=''):
        return NoOpCounter(self.name, name, unit=unit, description=description)

    # Create a non-recording up down counter with the requested metadata.
    def create_up_down_counter(self, name, unit='', description=''):
        return NoOpUpDownCounter(self.name, name, unit=unit, description=description)

    # Create a non-recording gauge with the requested metadata.
    def create_gauge(self, name, unit='', description=''):
        return NoOpGauge(self.name, name, unit=unit, description=description)

    # Create a non-recording histogram with the requested metadata.
    def create_histogram(self, name, unit='', description=''):
        return NoOpHistogram(self.name, name, unit=unit, description=description)


class MeterProvider:
    # Prepare resource metadata and collections of instruments and export readers.
    def __init__(self, resource=None):
        self.resource = resource or {}
        self._instruments = []
        self._readers = []

    # Create a named meter, returning an inert meter when telemetry is disabled.
    def get_meter(self, name):
        if not _telemetry_enabled():
            return NoOpMeter(name)
        return Meter(self, name)

    # Bind a reader to this provider before retaining it for lifecycle management.
    def add_metric_reader(self, reader):
        reader._bind(self)
        self._readers.append(reader)

    # Retain an instrument for future collection and return it to the caller.
    def _register(self, instrument):
        self._instruments.append(instrument)
        return instrument

    # Collect every instrument's current points while telemetry is enabled.
    def collect(self):
        if not _telemetry_enabled():
            return []
        metrics = []
        for instrument in self._instruments:
            metrics.append(instrument.collect())
        return metrics

    # Shut down each reader and its associated export resources.
    def shutdown(self):
        for reader in self._readers:
            reader.shutdown()


class NoOpMeterProvider:
    # Retain resource metadata for a provider that performs no telemetry export.
    def __init__(self, resource=None):
        self.resource = resource or {}

    # Return a named inert meter so callers can keep their instrumentation path.
    def get_meter(self, name):
        return NoOpMeter(name)

    # Acknowledge reader registration without enabling metric collection.
    def add_metric_reader(self, reader):
        return True

    # Return the supplied instrument without retaining it for collection.
    def _register(self, instrument):
        return instrument

    # Return no metric data because collection is disabled.
    def collect(self):
        return []

    # Acknowledge shutdown; this inert telemetry object owns no export resources.
    def shutdown(self):
        return True
