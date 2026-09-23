"""Explicit task ownership; no dependency on asyncio task introspection."""
try:
    import asyncio
except ImportError:
    import uasyncio as asyncio
import time


async def call(function, *args, **kwargs):
    result = function(*args, **kwargs)
    # MicroPython coroutines are generators; CPython exposes __await__.
    if hasattr(result, "__await__") or hasattr(result, "send"):
        return await result
    return result


def now_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.monotonic() * 1000)


def elapsed_ms(start):
    now = now_ms()
    return time.ticks_diff(now, start) if hasattr(time, "ticks_diff") else now - start


class TaskRegistry:
    def __init__(self, history_limit=32, max_active=64):
        self.records = {}
        self.history_limit = history_limit
        self.max_active = max_active
        self._next_id = 1

    def spawn(self, name, function, *args, kind="job", owner=None):
        active = sum(not r["done"].is_set() for r in self.records.values())
        # Leave capacity for HTTP/shell controls even when workflows saturate the node.
        limit = self.max_active - 8 if kind in ("operation", "flow") else self.max_active
        if active >= max(1, limit):
            raise RuntimeError("task capacity reached")
        task_id = self._next_id
        self._next_id += 1
        record = {"id": task_id, "name": name, "kind": kind, "owner": owner,
                  "state": "pending", "started": now_ms(), "result": None,
                  "error": None, "done": asyncio.Event(), "task": None}
        self.records[task_id] = record

        async def run():
            try:
                record["state"] = "running"
                record["result"] = await call(function, *args)
                record["state"] = "succeeded"
            except asyncio.CancelledError:
                record["state"] = "cancelled"
            except Exception as error:
                record["state"] = "failed"
                record["error"] = str(error)
            finally:
                record["duration_ms"] = elapsed_ms(record["started"])
                record["done"].set()
                self._prune()
        record["task"] = asyncio.create_task(run())
        return task_id

    def _prune(self):
        completed = [i for i, r in self.records.items() if r["done"].is_set() and r["kind"] not in ("service", "runtime", "app")]
        for task_id in completed[:-self.history_limit] if self.history_limit else completed:
            del self.records[task_id]

    def describe(self, task_id):
        r = self.records[task_id]
        return {"id": r["id"], "name": r["name"], "kind": r["kind"],
                "owner": r["owner"], "state": r["state"], "result": r["result"],
                "error": r["error"], "elapsed_ms": r.get("duration_ms", elapsed_ms(r["started"]))}

    def snapshot(self, include_done=False):
        return [self.describe(i) for i, r in self.records.items()
                if include_done or not r["done"].is_set()]

    async def wait(self, task_id):
        record = self.records[task_id]
        await record["done"].wait()
        if record["state"] == "failed":
            raise RuntimeError(record["error"])
        if record["state"] == "cancelled":
            raise asyncio.CancelledError()
        return record["result"]

    async def cancel(self, task_id):
        record = self.records[task_id]
        if not record["done"].is_set():
            # Let the wrapper enter its try/finally before cancellation.
            await asyncio.sleep(0)
            if not record["done"].is_set():
                record["task"].cancel()
            await record["done"].wait()

    async def cancel_kinds(self, kinds):
        ids = [i for i, r in self.records.items()
               if r["kind"] in kinds and not r["done"].is_set()]
        for task_id in ids:
            if task_id in self.records:
                await self.cancel(task_id)
