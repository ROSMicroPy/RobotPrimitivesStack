# Nodes and Manifests

A node manifest (`rp.node/v1`) describes a complete deployment. Service manifests (`rp.service/v1`) describe reusable contracts. JSON is the device format; component YAML files are useful for authoring and reviewing service definitions.

## Node manifest fields

| Field | Meaning |
| --- | --- |
| `identity` | Entity and unique node name |
| `resources` | Platform resources such as an I2C bus |
| `components` | Embedded reusable service contracts |
| `services` | Instances, implementations, constructor arguments, configuration and bindings |
| `runtime` | Shared listeners and infrastructure |
| `signals` | Routes, transport adapters and optional bridges |
| `apps` | Resident or one-off application factories |
| `flows` | Declarative behavior graphs |
| `execution` | Distributed peers, exposed operations and leases |

The following is a **fragment**, not a complete bootable manifest:

```json
{
  "identity": {"entity": "SlideDemo", "node": "node1"},
  "services": {
    "slide": {
      "component": "linear_slide",
      "bindings": {"motor": "motor", "position": "position"},
      "config": {
        "min_position_m": 0.03,
        "max_position_m": 0.3,
        "max_steps": 100000
      }
    }
  }
}
```

Use `examples/slide_nodes/node1.device.json` as a complete device example. Its companion `node2.device.json` describes the client.

## Load a node

Inside an existing async entry point:

```python
from rpstack.node_runtime import NodeRuntime

node = NodeRuntime.load('/lib/slide_node1.json')
await node.boot()
try:
    await node.wait()
finally:
    await node.shutdown()
```

For an application that owns the event loop, `run_manifest(path)` is the blocking boot entry. `run_manifests([path1, path2])` hosts multiple manifests on one loop. Do not run these alongside the background `slide_nodes` launcher.

## Bindings and ownership

A required capability can be bound automatically when exactly one compatible provider matches. Explicit bindings select a specific service instance. Missing, ambiguous, incompatible, or cyclic dependencies are rejected. Shared resources use references such as `{"$resource": "carriage_bus"}`.

Each entity/node pair must be unique. A node's service ID, such as `slide`, is local to that node. `NodeHost` can host multiple logical nodes in one process, but it does not make conflicting peripheral ownership safe.
