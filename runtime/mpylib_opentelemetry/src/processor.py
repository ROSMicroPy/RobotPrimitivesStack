# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#

try:
    import _thread
except ImportError:
    _thread = None

try:
    import utime as _time
except ImportError:
    import time as _time


def _telemetry_enabled():
    try:
        from .api import is_telemetry_enabled

        return is_telemetry_enabled()
    except Exception:
        return True


class SimpleSpanProcessor:
    def __init__(self, exporter, batch_size=16):
        self._exporter = exporter
        self._batch_size = max(1, int(batch_size or 1))
        self._pending_spans = []

    def on_end(self, span, resource=None):
        if not _telemetry_enabled():
            self._pending_spans = []
            return 0
        self._pending_spans.append(span)
        should_flush = len(self._pending_spans) >= self._batch_size
        if getattr(span, 'parent_span_id', None) is None:
            should_flush = True
        if not should_flush:
            return 0
        pending = self._pending_spans
        self._pending_spans = []
        status = self._exporter.export(pending, resource=resource)
        if not _telemetry_enabled():
            self._pending_spans = []
        elif not status:
            self._pending_spans = pending + self._pending_spans
        return status

    def shutdown(self):
        if _telemetry_enabled() and self._pending_spans:
            pending = self._pending_spans
            self._pending_spans = []
            self._exporter.export(pending)
        if hasattr(self._exporter, 'shutdown'):
            self._exporter.shutdown()


class SimpleLogProcessor:
    def __init__(self, exporter, failure_callback=None):
        self._exporter = exporter
        self._failure_callback = failure_callback

    def emit(self, record, resource=None):
        if not _telemetry_enabled():
            return 0
        status = self._exporter.export([record], resource=resource)
        if not status:
            self._emit_fallback([record], resource=resource)
        return status

    def set_fallback_handler(self, callback):
        self._failure_callback = callback
        return True

    def _emit_fallback(self, records, resource=None):
        if not callable(self._failure_callback):
            return 0
        emitted = 0
        for record in records:
            try:
                self._failure_callback(record, resource=resource)
                emitted += 1
            except Exception:
                continue
        return emitted

    def shutdown(self):
        if hasattr(self._exporter, 'shutdown'):
            self._exporter.shutdown()


def _sleep_ms(duration_ms):
    if hasattr(_time, "sleep_ms"):
        _time.sleep_ms(max(0, int(duration_ms)))
        return
    _time.sleep(max(0, int(duration_ms)) / 1000.0)


class _QueuedProcessorBase:
    def __init__(
        self,
        exporter,
        batch_size=16,
        queue_size=128,
        flush_interval_ms=200,
        auto_start=True,
        failure_callback=None,
    ):
        self._exporter = exporter
        self._batch_size = max(1, int(batch_size or 1))
        self._queue_size = max(1, int(queue_size or 1))
        self._flush_interval_ms = max(1, int(flush_interval_ms or 1))
        self._failure_callback = failure_callback
        self._pending_entries = []
        self._dropped_count = 0
        self._shutdown_requested = False
        self._worker_running = False
        self._worker_available = bool(_thread and hasattr(_thread, "start_new_thread"))
        self._lock = None
        if _thread and hasattr(_thread, "allocate_lock"):
            try:
                self._lock = _thread.allocate_lock()
            except Exception:
                self._lock = None
        if auto_start:
            self.start_worker()

    @property
    def dropped_count(self):
        return self._dropped_count

    @property
    def worker_running(self):
        return self._worker_running

    def snapshot(self):
        if self._lock is None:
            queue_len = len(self._pending_entries)
        else:
            with self._lock:
                queue_len = len(self._pending_entries)
        return {
            "queue_len": queue_len,
            "queue_size": self._queue_size,
            "batch_size": self._batch_size,
            "flush_interval_ms": self._flush_interval_ms,
            "dropped_count": self._dropped_count,
            "worker_running": bool(self._worker_running),
            "worker_available": bool(self._worker_available),
        }

    def set_fallback_handler(self, callback):
        self._failure_callback = callback
        return True

    def start_worker(self):
        if not self._worker_available or self._worker_running:
            return False
        self._shutdown_requested = False
        try:
            _thread.start_new_thread(self._worker_loop, ())
        except Exception:
            self._worker_running = False
            return False
        self._worker_running = True
        return True

    def _worker_loop(self):
        try:
            while not self._shutdown_requested:
                self.drain_once()
                _sleep_ms(self._flush_interval_ms)
            while self.drain_once():
                pass
        finally:
            self._worker_running = False

    def _enqueue(self, item, resource=None):
        if not _telemetry_enabled():
            self._pending_entries = []
            return 0
        entry = {"item": item, "resource": resource}
        if self._lock is None:
            return self._enqueue_unlocked(entry)
        with self._lock:
            return self._enqueue_unlocked(entry)

    def _enqueue_unlocked(self, entry):
        if len(self._pending_entries) >= self._queue_size:
            self._pending_entries.pop(0)
            self._dropped_count += 1
        self._pending_entries.append(entry)
        return 1

    def _take_batch(self):
        if self._lock is None:
            return self._take_batch_unlocked()
        with self._lock:
            return self._take_batch_unlocked()

    def _take_batch_unlocked(self):
        if not self._pending_entries:
            return []
        batch = self._pending_entries[: self._batch_size]
        self._pending_entries = self._pending_entries[self._batch_size :]
        return batch

    def _requeue_front(self, entries):
        if not entries:
            return
        if self._lock is None:
            self._requeue_front_unlocked(entries)
            return
        with self._lock:
            self._requeue_front_unlocked(entries)

    def _requeue_front_unlocked(self, entries):
        merged = list(entries) + self._pending_entries
        if len(merged) > self._queue_size:
            overflow = len(merged) - self._queue_size
            self._dropped_count += overflow
            merged = merged[: self._queue_size]
        self._pending_entries = merged

    def _export_batch(self, entries):
        if not entries:
            return 0
        current_resource = entries[0].get("resource")
        current_items = []
        status = 1
        for entry in entries:
            entry_resource = entry.get("resource")
            if current_items and entry_resource != current_resource:
                result = self._exporter.export(current_items, resource=current_resource)
                if not result:
                    return 0
                current_resource = entry_resource
                current_items = []
            current_items.append(entry.get("item"))
        if current_items:
            status = self._exporter.export(current_items, resource=current_resource)
        return status

    def drain_once(self):
        if not _telemetry_enabled():
            self._pending_entries = []
            return 0
        entries = self._take_batch()
        if not entries:
            return 0
        status = self._export_batch(entries)
        if not _telemetry_enabled():
            self._pending_entries = []
        elif not status:
            self._requeue_front(entries)
        return len(entries)

    def flush(self):
        while True:
            drained = self.drain_once()
            if not drained:
                return True

    def shutdown(self):
        self._shutdown_requested = True
        self.flush()
        if hasattr(self._exporter, 'shutdown'):
            self._exporter.shutdown()


class QueuedSpanProcessor(_QueuedProcessorBase):
    def on_end(self, span, resource=None):
        return self._enqueue(span, resource=resource)


class QueuedLogProcessor(_QueuedProcessorBase):
    def emit(self, record, resource=None):
        return self._enqueue(record, resource=resource)

    def drain_once(self):
        if not _telemetry_enabled():
            self._pending_entries = []
            return 0
        entries = self._take_batch()
        if not entries:
            return 0
        status = self._export_batch(entries)
        if not _telemetry_enabled():
            self._pending_entries = []
        elif not status:
            self._emit_fallback(entries)
        return len(entries)

    def _emit_fallback(self, entries):
        if not callable(self._failure_callback):
            return 0
        emitted = 0
        for entry in entries:
            try:
                self._failure_callback(entry.get("item"), resource=entry.get("resource"))
                emitted += 1
            except Exception:
                continue
        return emitted


class MetricReader:
    def __init__(self, exporter):
        self._exporter = exporter
        self._provider = None

    def _bind(self, provider):
        self._provider = provider

    def collect(self):
        if not _telemetry_enabled() or self._provider is None:
            return None
        metrics = self._provider.collect()
        if not metrics:
            return None
        return self._exporter.export(metrics, resource=self._provider.resource)

    def shutdown(self):
        if hasattr(self._exporter, 'shutdown'):
            self._exporter.shutdown()


class NoOpMetricReader:
    def __init__(self):
        self._provider = None

    def _bind(self, provider):
        self._provider = provider

    def collect(self):
        return None

    def shutdown(self):
        return True
