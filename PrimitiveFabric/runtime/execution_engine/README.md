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
runtime actions. STEP/DIR pulses and VL53L4CD readiness waits yield.


## Distributed workflows

The engine owns one coordinator per run, not one global engine per chip.
A graph step's `node` selects a peer; absent `node`, it executes locally.
`RemoteActions` dispatches correlated, leased operations through the shared
signal bus. Workers validate and supervise them with their local runtime.
Coordinator transitions emit revisioned `_rp.state` signals for other nodes.

See [entity signals and distributed execution](../signals/README.md) for manifest
configuration, correlated waits, reset fencing, observations, and failure limits.

Use `SignalBus` from `rpstack.signals`; each engine exposes its shared bus as `engine.signals`.

## Confirmed remote cancellation

`RemoteActions.invoke(..., cancel_event=event, cancel_timeout_s=3)` optionally
waits for worker confirmation after cancellation instead of immediately abandoning
the result subscription. The event must expose `is_set()`. Once set, the caller
stops renewing the action lease and sends cancellation requests without resending
the operation. A worker-confirmed cleanup raises `RemoteCancelled`; a completion
that wins the race still returns its result. Timeout is an unconfirmed outcome.
Older workers without the explicit cancellation result flag cannot provide this
confirmation. Ordinary task cancellation retains the existing best-effort cancel
plus receiver-lease behavior. `probe(target, timeout_s)` checks admission and
returns the worker generation without allocating operation history.
