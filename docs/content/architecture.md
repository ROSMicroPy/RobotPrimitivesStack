# Somatic Mesh architecture

Somatic Mesh hosts Actors with assigned Behaviors across connected small devices. Capability services expose hardware and computation; managed operations, workflows, signals, and discovery coordinate their use. ROSMicroPy supplies the embedded ROS foundation, and ESP-NOW supports local communication without an access point or IP setup.

## Responsibilities

| Layer | Responsibility |
| --- | --- |
| The Loom | Authoring, deployment tooling, and observation |
| Fabric management | Discovery and public state; placement reconciliation and recovery are roadmap work |
| Host execution | `DeviceHost`, `FabricNode`, `Actor`, lifecycle supervision, and tasks |
| Behaviors | Application responses, sequences, and protocol handling |
| Capabilities | Services, drivers, adapters, and composites with versioned contracts |
| Platform | Firmware, hardware resources, networking, storage, and boot |
| Communication and visibility | Signals, transport adapters, HTTP/shell controls, and telemetry |

## Repository groups

| Group | Packages and responsibility |
|---|---|
| `foundation` | `interfaces` defines capability contracts and measurement types; `support` provides lightweight asyncio, JSON, invocation, and clock helpers. |
| `runtime` | `fabric_node` constructs and supervises nodes; `execution_engine` manages operations and workflows; `signals` handles envelopes and subscriptions; `catalog` provides discovery and composition models. |
| `transports` | `espnow` and `ros_signals` carry signal envelopes. |
| `control` | `http` and `shell` expose node controls. |
| `platform` | `bootmgr` and `env` provide startup and configuration storage. |
| `observability` | `opentelemetry` provides tracing, metrics, and logs. |
| `services` | Distance and motor providers, a distance-to-position adapter, and the linear-slide composite. |
| `behaviors` | `robot_gateway` exposes robot discovery over HTTP; `slide_commands` provides slide command and client applications. |
| `spec` | Node and service manifest schemas. |
| `examples` (repository root) | Device deployments and host simulations. |

Each package has one source tree under `src/somatic_mesh`, a MIP source map, documentation, and relevant host tests. Service implementations live in `service.py`; package initializers expose their public classes. Drivers remain inside their owning service package.

## Dependency boundaries

Foundation packages import no runtime, service, or application packages. Services use contracts and portable support directly. Composites consume capability interfaces. The node runtime constructs providers and binds consumers to them. Applications submit operations through nodes. Transports carry signals; control interfaces expose node actions.

A slide client can install `somatic_mesh.behaviors.slide_commands` without installing the slide hardware service. The slide service itself has no dependency on its orchestration applications.

## Vocabulary and naming conventions

| Concept | Code convention |
| --- | --- |
| Product / source root | Somatic Mesh / `SomaticMesh/` |
| Python namespace | `somatic_mesh` |
| Runtime host | `FabricNode`, package `somatic_mesh.fabric_node` |
| Shared device process | `DeviceHost` |
| Logical participant | `Actor`, manifest `actors`, node-local `id` |
| Assigned implementation | `Behavior` subclasses with a `Behavior` suffix; manifest `behavior` entry point |
| Workflow | Named `flows` graph; graph `nodes` are steps |
| Execution | Managed task with a task ID; Actor execution uses task kind `actor` |
| Contracts | `somatic.node/v1` and `somatic.service/v1` |
| Runtime signals | Reserved `_sm.` prefix |
| ROS interfaces | `somatic_mesh_interfaces`; default namespace `/somatic_mesh` |

A Device is physical hardware. A Fabric Node has an entity/node identity and hosts services and Actors. An Actor has a node-local identity and owns a Behavior instance; it is neither a service nor a task. Its address is `(entity, node, actor)`. Signals route between nodes; Actor-independent placement and addressing are roadmap work.

`ServiceRegistry` resolves capabilities. `Catalog` reports observed nodes, Actor assignments, and services. `PhysicalComponent` and `CompositionRegistry` model hardware assemblies and mount claims. Discovery excludes Actor configuration and is not permission to operate.

## Lifecycle

Providers start before consumers and stop in reverse dependency order. Service stop/reset keeps control facilities reachable. Full shutdown releases applications, transports, and runtime resources as well. Work runs through managed tasks on the node's cooperative event loop, with dedicated pulse workers for blocking motor batches.

## Installation and validation

Use package manifests at their canonical locations. Remote `package.json` files declare dependencies; `package.local.json` files describe local source maps. Example manifests list the full local installation set.

Run `python3 tools/check_architecture.py` to validate package maps and isolated installations. Run `python3 tools/run_tests.py` for host regression suites. Device memory, physical motor timing, sensor feedback, and radio behavior require hardware validation.

## Deployment boundaries and roadmap

Node manifests define fixed Actor placement, service bindings, resources, and transports. Multiple Fabric Nodes on one DeviceHost share an interpreter and filesystem. Local resource claims arbitrate operations; they do not establish cross-host ownership after a partition.

The Loom need not remain connected for local deployed Behaviors to run. ROS-dependent Behaviors require their ROS communication path. ESP-NOW peers share a radio channel; bounded relaying extends configured signal delivery beyond direct neighbors. End-to-end latency and physical stop timing require hardware measurement.

The [Fabric management roadmap](fabric-management.html) specifies application/hardware/deployment separation, exact delivery, controlled activation, and recovery. Alternative-host restart needs eligible resources and stale-instance fencing. Stateful handoff needs checkpoint/restore. Physical wiring constrains relocation, and unsaved state cannot be recovered from a dead device.
