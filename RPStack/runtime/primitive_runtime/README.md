# Primitive runtime

`NodeRuntime.load(path)` loads a complete `rp.node/v1` application. Use
`run_manifest(path)` from the device's `/main.py`, or `await node.boot()` inside
an existing event loop. See [the linear slide node](../../../TestApps/linear_slide/README.md)
for an executable manifest and installation instructions.

The node manifest embeds reusable `rp.service/v1` contracts under `components`.
Each `services` entry references a component, optional driver implementation,
constructor arguments, configuration values, and role-to-service `bindings`.
Configuration is validated and defaults are applied before initialization.
`{"$resource":"name"}` resolves a shared resource declared under `resources`.
MicroPython consumes JSON without YAML dependencies.

`ServiceSupervisor` resolves capability bindings and dependency order. Its
`prepare`, `start`, `stop`, `reset`, `status`, and `invoke` methods are async.
`submit` immediately reserves resource claims and returns a tracked operation ID.
All exclusive operations claim their transitive dependencies, preventing a
motor command from racing a composite slide operation. Conflicts fail instead
of accumulating unbounded queues. `invoke` awaits the same managed operation
and propagates cancellation to it.

Every application service has a resident task. A service may define async
`run()` for polling; otherwise its task waits until shutdown. Runtime services
implement `start`, `run`, and `stop`, and receive the node in their constructor.
The node health task stops the application if a resident service fails. HTTP
and shell remain outside application stop/reset so controls remain reachable.

Stopping closes admission, cancels workflows and operations, then stops and
releases initialized services in reverse order. Reset performs the same cleanup
and constructs fresh instances. Failed partial startup also cleans up initialized
instances. `shutdown` additionally closes runtime services and platform resources.

`ManifestTestRunner.run` is async and invokes the supervisor's managed operations.
Service test declarations retain their existing explicit hardware-test opt-in.


Node manifests also declare `identity`, `signals`, and optional `execution`
settings. Signal transports start after runtime services (including Wi-Fi),
and before autostart flows. A service with `inject_signals: true` receives the
entity bus as its `signals` constructor argument. See the
[signal runtime](../signals/README.md) for mesh/ROS combinations and robot-wide
workflow execution.

## Multiple logical nodes and one-off tasks

`NodeHost` / `run_manifests([path, ...])` host multiple independent manifests on
one event loop. Each node keeps its own services, tasks, resources, and identity;
the host rejects duplicate entity/node pairs. Use the signal runtime's
`rpstack.signals.inprocess:InProcessTransport` for communication within a process,
or existing network transports across devices. List providers before clients.

An app may declare `"mode": "oneshot"` (default: `"resident"`). Successful
completion is expected for these apps. `await node.wait()` waits for every app
on a task-only node and propagates errors; resident/mixed nodes wait for shutdown.
The manifest runners automatically shut down completed task-only nodes while
other nodes continue running. See the [two-node slide example](../../../TestApps/slide_nodes/README.md).
