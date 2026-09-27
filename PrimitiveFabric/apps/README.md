# Node apps

`RPStack/apps/<app>/src/rpstack/apps/<app>/` is the home for reusable node
applications that orchestrate node capabilities. `RPStack/services` contains reusable
hardware primitives and capability providers; `RPStack/runtime` contains shared
lifecycle, signals, discovery, and execution. `RPStack/control` provides HTTP and shell interfaces; `RPStack/transports` provides ESP-NOW and ROS signal adapters. `examples` holds complete
deployments and hardware examples that assemble these layers.

A node can run multiple apps and primitive services concurrently on its single
asyncio loop. Each app exports a factory `(node, **config)` and async `start()`,
`run()`, and `stop()` methods. `start()` prepares resources and returns; `run()`
remains resident and yields; `stop()` releases only resources owned by the app.
Never create another event loop or take ownership of a shared server/radio.

Declare apps in the node manifest, in dependency order:

```json
"apps": [
  {
    "id": "gateway",
    "entry_point": "rpstack.apps.robot_gateway:GatewayApp",
    "requires": ["http", "catalog"],
    "config": {"http": "http", "catalog": "catalog"}
  }
]
```

`requires` names runtime services or earlier apps. IDs are unique across both
lists. All factories and dependency references are checked before hardware is
initialized. Apps start after primitive services, runtime services and signal
transports. Instances are available in `node.apps` and `node.runtime_instances`.
Tasks are owned by app ID and visible in the existing task API and shell.

Node stop/reset controls primitive services and flows while internal apps remain
available (including the gateway and shell). App failure causes the node health
monitor to stop primitive services; restart the node to recover a failed resident
app. Shutdown cancels resident tasks and stops apps in reverse startup order,
including partially started apps after a boot error.

The linear-slide deployment runs its motor, distance sensor, position adapter,
and slide controller alongside the gateway app. Test interfaces can similarly be
implemented as apps, reusing `node.submit`, `node.status`, and the shared HTTP
runtime. Gateway-only nodes may use empty `services` and `components` objects.
