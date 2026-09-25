# Apps and Behaviors

Apps implement node-level behavior using services and shared runtime facilities. Reusable apps live under `RPStack/apps/`; complete deployments live under `examples/`. Some domain-specific apps, such as the slide command adapter, live beside their service.

## App lifecycle

An app factory receives `(node, **config)` and supplies async `start()`, `run()`, and `stop()` methods. `start()` prepares resources and returns; `run()` does the ongoing work; `stop()` releases app-owned resources. The runtime owns the event loop and shared transports.

```python
class AnnounceApp:
    def __init__(self, node):
        self.node = node

    async def start(self):
        pass

    async def run(self):
        self.node.publish_signal('app.ready', {'ready': True})

    async def stop(self):
        pass
```

Declare this example as `mode: oneshot`, since its `run()` returns intentionally. A resident app should keep running cooperatively.

Manifest fragment:

```json
{
  "apps": [{
    "id": "announce",
    "entry_point": "my_apps:AnnounceApp",
    "mode": "oneshot",
    "config": {}
  }]
}
```

## Dependencies and modes

Apps start after primitive services, runtime services, and signal transports. An app's `requires` list names runtime services or earlier apps. IDs must be unique across those lists.

Resident is the default mode. Unexpected resident failure triggers the node's health handling. For a task-only node, `await node.wait()` waits for its one-off apps and propagates failures. Manifest runners shut down completed task-only nodes while resident peers continue.

## Declarative flows

Use a flow when behavior is naturally a graph of operations, waits, and branches. Use an app when the behavior needs custom protocol handling or state. A distributed flow has one coordinator; other nodes execute its requested actions. There is no automatic coordinator failover.

See [Runtime](runtime.html) for task supervision and [Multiple Devices](deployment.html) for transport placement.
