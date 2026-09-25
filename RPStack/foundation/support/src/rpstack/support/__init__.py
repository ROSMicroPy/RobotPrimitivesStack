"""Lightweight cooperative-call and monotonic-clock portability helpers."""
try:
    import asyncio
except ImportError:
    import uasyncio as asyncio
import time


# Invoke a capability uniformly whether it returns a value or a MicroPython/CPython coroutine.
async def call(function, *args, **kwargs):
    result = function(*args, **kwargs)
    # MicroPython coroutines are generators; CPython exposes __await__.
    if hasattr(result, "__await__") or hasattr(result, "send"):
        return await result
    return result


# Read a monotonic millisecond clock using the platform's available timer.
def now_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.monotonic() * 1000)


# Measure elapsed time with wraparound handling on MicroPython tick counters.
def elapsed_ms(start):
    now = now_ms()
    return time.ticks_diff(now, start) if hasattr(time, "ticks_diff") else now - start


try:
    import ujson as json
except ImportError:
    import json
