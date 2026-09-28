# Somatic Mesh

**A distributed compute framework and management system for small devices.**

*Design in The Loom. Bring Actors and Behaviors to life across the Fabric.*

Somatic Mesh coordinates sensors, actuators, and computation across connected devices. Actors perform assigned Behaviors, exchange signals, and invoke capability services. Deploy a sequence across devices and let it run without keeping The Loom connected.

ROSMicroPy is a foundational part of the embedded ROS architecture. ROS transport and typed gateways connect the Fabric to ROS robots, while ESP-NOW supports local communication without an access point or IP configuration. Deployments select the transports and external participants their Behaviors require.

## Actors, Behaviors, and hosts

| Concept | Responsibility | Python/API name |
| --- | --- | --- |
| Device | Physical board or computer | Hardware and resource configuration |
| Device host | Hosts Fabric Nodes on one event loop | `DeviceHost` |
| Fabric Node | Assembles capabilities and hosts Actors | `FabricNode` |
| Actor | Owns a named Behavior instance and its execution | `Actor`, `node.actors[id]` |
| Behavior | Implements preparation, work, and cleanup | `Behavior`, `start/run/stop` |
| Workflow | Sequences operations and signals | `WorkflowBehavior`, manifest `flows` |
| Task | Tracks one execution and its outcome | `TaskRegistry` |
| Capability | Versioned contract provided by a service | `somatic.service/v1` |

Actor IDs are unique within a Fabric Node. An Actor's address is `(entity, node, actor)`; signals route by entity and node, with application names and correlation IDs identifying exchanges. Placement is explicit. Actor ownership of a Behavior does not imply automatic relocation or exclusive authority over a remote actuator.

## Define an Actor

A fragment of a `somatic.node/v1` manifest:

```json
{
  "actors": [{
    "id": "carriage",
    "behavior": "somatic_mesh.behaviors.slide_commands:SlideCommandBehavior",
    "version": "0.1.0",
    "mode": "resident",
    "config": {"service": "slide"}
  }]
}
```

The Fabric Node supplies an Actor to the Behavior factory. The Behavior accesses shared services, signals, and managed operations through `actor.node`. Configuration belongs to the Actor assignment and is excluded from public discovery.

```python
from somatic_mesh.fabric_node import DeviceHost, FabricNode
from somatic_mesh.support import Behavior

class AnnounceBehavior(Behavior):
    async def run(self):
        self.node.publish_signal('participant.ready', {'actor': self.actor.id})
```

Declare a Behavior that returns normally as `oneshot`. Resident Behaviors run cooperatively until shutdown; unexpected completion triggers host-node health handling.

## Repository structure

`SomaticMesh/` contains independently installable packages:

- `foundation/`: capability contracts, measurement types, and portable Behavior support.
- `runtime/`: Fabric Nodes, Actors, operations, workflows, signals, and discovery.
- `behaviors/`: slide commands, Fabric discovery gateway, and typed ROS gateway.
- `transports/`: ESP-NOW and ROS signal delivery.
- `control/`: HTTP and shell interfaces.
- `platform/` and `observability/`: boot, configuration, and telemetry.
- `services/`: drivers, adapters, and composite capability providers.
- `spec/`: node and service manifest schemas.

`TheLoom/` is the authoring-environment submodule; `ROSMicroPy/` supplies the embedded ROS foundation. `examples/` contains host simulations and device deployments. `ros2/somatic_mesh_interfaces/` defines typed ROS messages and actions.

## Explore and validate

Start with [getting started](docs/content/getting-started.md), the [Robie1 simulation](examples/robie1/README.md), or the [linear-slide deployment](examples/slide_nodes/README.md). Read [Actors and Behaviors](docs/content/actors.md) and the [architecture](SomaticMesh/ARCHITECTURE.md) for API contracts and boundaries.

```sh
git submodule update --init ROSMicroPy
python3 -m pip install -r tools/requirements-test.txt
python3 tools/validate_manifests.py
python3 tools/check_architecture.py
python3 tools/run_tests.py
python3 docs/build.py
```

Packages install into `somatic_mesh`. From the repository root:

```sh
mpremote mip install SomaticMesh/services/distance_sensor/package.json
```

[Implementation reference](IMPLEMENTATION.md) covers service manifests and capability composition. [Fabric management](docs/content/fabric-management.md) describes the roadmap for application/deployment separation, controlled activation, alternative-host recovery, and stateful handoff. Those management features require additional implementation; moving computation cannot restore a motor connection on a failed board.
