# Portable execution support

`rpstack.support` supplies `asyncio`, `call`, `now_ms`, `elapsed_ms`, and `json` to independently installed packages. Importing it does not load workflows, signal transport, or the node runtime.

Use `await call(provider.operation, ...)` to invoke a provider that may return either an immediate value or a MicroPython/CPython coroutine. Use the monotonic clock helpers for durations; they handle MicroPython tick wraparound.
