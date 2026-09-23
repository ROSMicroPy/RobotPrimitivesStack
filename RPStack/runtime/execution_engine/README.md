# Execution engine

The engine uses one asyncio event loop on CPython or MicroPython. There are no
worker threads. `TaskRegistry` owns services, runtime listeners, HTTP requests,
operations, shell commands, and workflows. It retains 32 completed job records
and reserves task capacity for control requests. `ps` displays active tasks;
`GET /api/tasks` includes retained results and errors.

`ExecutionEngine` runs manifest graphs. A node may invoke a service operation,
then wait for a named signal, then publish a signal, and select `next`. Failures
and timeouts follow `on_error` when declared. Independent flows run concurrently.
Every flow subscribes before executing its first action, so a signal published
by that action is retained until the wait. Events published before a flow starts
are not replayed. Each subscriber has a bounded queue; overflow fails explicitly.
Cancellation bypasses error routing and always removes subscriptions.

```json
{
  "start": "move",
  "autostart": false,
  "nodes": {
    "move": {
      "service": "slide", "operation": "move_to",
      "arguments": {"target": 0.1},
      "wait_for": "operator.continue", "timeout_s": 60,
      "next": "observe"
    },
    "observe": {"service": "slide", "operation": "observe_position"}
  }
}
```

Actions must be cooperative: quick synchronous functions are supported, but
blocking functions do not become nonblocking merely by being placed in a task.
Do not put synchronous loops, sleeps, socket reads, or long hardware waits in
runtime actions. STEP/DIR pulses and VL53L4CD readiness waits now yield.
