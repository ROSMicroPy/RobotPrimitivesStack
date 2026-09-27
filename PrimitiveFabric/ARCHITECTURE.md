# Somatic Mesh architecture

Somatic Mesh is a distributed compute framework and management system for small devices. Its target model deploys Actors with assigned Behaviors across the Fabric, authored and observed through The Loom.

The existing RPStack implementation assembles logical nodes from independently installed packages. Drivers access hardware, services expose capabilities, adapters transform measurements, composites coordinate providers, and apps or flows orchestrate work. These remain the runtime foundation. Product terminology does not rename Python packages, schemas, or current runtime classes.

## Architectural responsibilities

| Responsibility | Current foundation and proposed evolution |
| --- | --- |
| Authoring and observation | Robot Architect is the existing environment; The Loom is its proposed product name, with ILA as a proposed assistant |
| Fabric management | Proposed placement, authoritative ownership, controlled activation, recovery, and deployment reconciliation |
| Host execution | Existing node assembly, lifecycle, managed tasks, operations, workflows, and resource claims; explicit Actor hosting remains proposed |
| Capabilities | Existing services, drivers, adapters, and composites retain their contracts and hardware ownership |
| Platform | Firmware, board support, storage, networking, and device resources |
| Communication and visibility | Transports, signals, control interfaces, discovery, and telemetry span the other responsibilities |

Application definitions should express Actors, Behaviors, connections, constraints, and recovery policy. Device profiles should express hardware and resources. Deployment plans should assign hosts, bindings, and exact versions. Today's node manifests combine these concerns; the separation is a design direction, not a supported replacement schema.

## Repository groups

| Group | Packages and responsibility |
|---|---|
| `foundation` | `interfaces` defines capability contracts and measurement types; `support` provides lightweight asyncio, JSON, invocation, and clock helpers. |
| `runtime` | `node_runtime` constructs and supervises nodes; `execution_engine` manages operations and workflows; `signals` handles envelopes and subscriptions; `catalog` provides discovery and composition models. |
| `transports` | `espnow` and `ros_signals` carry signal envelopes. |
| `control` | `http` and `shell` expose node controls. |
| `platform` | `bootmgr` and `env` provide startup and configuration storage. |
| `observability` | `opentelemetry` provides tracing, metrics, and logs. |
| `services` | Distance and motor providers, a distance-to-position adapter, and the linear-slide composite. |
| `apps` | `robot_gateway` exposes robot discovery over HTTP; `slide_commands` provides slide command and client applications. |
| `spec` | Node and service manifest schemas. |
| `examples` (repository root) | Device deployments and host simulations. |

Each package has one source tree under `src/rpstack`, a MIP source map, documentation, and relevant host tests. Service implementations live in `service.py`; package initializers expose their public classes. Drivers remain inside their owning service package.

## Dependency boundaries

Foundation packages import no runtime, service, or application packages. Services use contracts and portable support directly. Composites consume capability interfaces. The node runtime constructs providers and binds consumers to them. Applications submit operations through nodes. Transports carry signals; control interfaces expose node actions.

A slide client can install `rpstack.apps.slide_commands` without installing the slide hardware service. The slide service itself has no dependency on its orchestration applications.

## Vocabulary

| Term | Meaning |
|---|---|
| Device | Physical board or host environment. |
| Fabric Node | Target runtime-host concept: an execution location for Actors; no separate API exists yet. |
| Logical node | Current manifest-defined assembly and identity; `NodeHost` can host several on one device. |
| Actor | Proposed stable participant with assigned Behavior, configuration, explicit state, message handling, and lifecycle. |
| Behavior | Implementation or workflow defining an Actor's work and responses; apps and flows are current building blocks. |
| Fabric | Connected runtime and management infrastructure; automatic placement and recovery remain proposed. |
| Service type | Reusable implementation and contract definition in a manifest's `components` map. |
| Service instance | Configured capability provider constructed on a node. |
| Driver | Hardware-specific backend owned by a service. |
| Capability | Versioned service interface and provider constraints. |
| Operation | Declared callable exposed by a service. |
| App | Orchestration code with a resident or one-shot lifecycle. |
| Workflow | Declarative operation/signal graph in `flows`; its `nodes` entries are workflow steps. |
| Task | Managed execution instance tracked by `TaskRegistry`. |
| Signal | Event envelope carried by `SignalBus`. |
| Deployment | Node manifests, resources, apps, and installed packages for a scenario. |

`ServiceRegistry` resolves service dependencies. `Catalog` describes discovered nodes. `PhysicalComponent` and `CompositionRegistry` model physical assemblies and mount claims.

## Lifecycle

Providers start before consumers and stop in reverse dependency order. Service stop/reset keeps control facilities reachable. Full shutdown releases applications, transports, and runtime resources as well. Work runs through managed tasks on the node's cooperative event loop, with dedicated pulse workers for blocking motor batches.

## Installation and validation

Use package manifests at their canonical locations. Remote `package.json` files declare dependencies; `package.local.json` files describe local source maps. Example manifests list the full local installation set.

Run `python3 tools/check_architecture.py` to validate package maps and isolated installations. Run `python3 tools/run_tests.py` for host regression suites. Device memory, physical motor timing, sensor feedback, and radio behavior require hardware validation.

## Management and recovery boundaries

The Loom should resolve and deliver exact software while onboard management permits operation and recovery without desktop or internet access. Start with one onboard coordinator and preinstall code on eligible fallback hosts. Coordinator failover is separate work.

Catalog discovery is observational, not authority to execute or take over. Existing action leases do not prevent two Actor instances from controlling the same machinery after a partition. Actor ownership requires explicit transfer and enforcement that rejects stale instances at resource boundaries.

Start with fixed placement and stable Actor addressing, then stateless restart elsewhere. Add explicit checkpoint/restore and planned handoff only for selected stateful Behaviors. Crash recovery cannot retrieve unsaved state from a dead device. Physical bindings constrain relocation, and moving CPU work does not remove local actuator power demand.

Multiple logical nodes share an interpreter and filesystem; they are not isolated failure domains. An Actor is not a renamed `NodeRuntime` or task, and each small driver need not become an Actor.

See the [Fabric management proposal](../docs/content/fabric-management.md), [bootstrap design](../docs/content/bootstrap.md), and [registry design](../docs/content/registries.md) for scope and milestones. These are proposed designs, not implemented guarantees.
