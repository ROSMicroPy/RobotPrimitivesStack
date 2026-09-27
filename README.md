# Somatic Mesh

**A distributed compute framework and management system for small devices.**

*Design in The Loom. Bring Actors and Behaviors to life across the Fabric.*

Somatic Mesh is being developed to coordinate connected devices as one system: what they do, how they respond to signals, and which software they run. Its intended programming model assigns **Behaviors** to **Actors** and deploys those Actors onto suitable runtime hosts across the **Fabric**. Physical computing is a central use case, from instrumented mechanisms to coordinated machines; the framework is broader than a particular controller board or robotics stack.

**The Loom** is the proposed product name for the authoring, deployment, and observation environment currently called Robot Architect. **ILA**, the Intelligent Loom Assistant, is the proposed assistant within The Loom. Deployed systems should operate without a desktop or internet connection.

## Project status

This repository contains the existing **RPStack** implementation (now stored under `PrimitiveFabric/`) that forms the foundation of Somatic Mesh. The product model is evolving; this documentation update does not rename packages or introduce Actor APIs. Keep using `rpstack`, `PrimitiveFabric/`, `rp.node/v1`, `rp.service/v1`, and the current Robot Architect extension names in commands and code.

| Available in the current implementation | Proposed evolution |
| --- | --- |
| Manifest-driven logical nodes and capability binding | Explicit Actor identities, Behavior versions, and lifecycle contracts |
| Service supervision, managed operations, resource claims, and cooperative tasks | Application definitions separated from hardware profiles and deployment plans |
| Signals, transport adapters, discovery, and leased remote actions | Stable Actor addressing, authoritative placement, and deployment reconciliation |
| Apps, workflows, HTTP/shell controls, and gateway discovery | Onboard controlled activation and restart on eligible alternative hosts |
| Manual package installation and device configuration | Exact software delivery through The Loom, selected stateful handoff, and resource-aware placement |

Discovery and remote-action leases do not establish Actor ownership or automatic failover. The runtime does not currently migrate arbitrary running Python code. See the [architecture](PrimitiveFabric/ARCHITECTURE.md) and [Fabric management design](docs/content/fabric-management.md) for the proposed boundaries and milestones.

## The mental model

- **Device:** a physical board or computer with processing, storage, power, and hardware connections.
- **Fabric Node:** a runtime host in the target model, providing an execution location for Actors. Existing logical nodes are implementation assemblies, not a new Actor abstraction.
- **Actor:** a logical participant with a stable identity, assigned Behavior, configuration, state, and lifecycle.
- **Behavior:** the implementation or workflow that defines what an Actor does and how it responds.
- **Capability:** a versioned contract for something a service can provide, such as observing position or commanding motion.
- **Fabric:** the runtime and management infrastructure that connects participants and, as the design develops, manages placement and recovery.

An Actor is not a task: a task is a tracked execution instance. An Actor may use several capabilities and run many operations over its lifetime. Small drivers and adapters do not each need their own Actor.

## A concrete example

A linear slide combines a motor, distance sensor, position adapter, and composite motion service. In the intended model, a carriage Actor is assigned a positioning Behavior that uses these capabilities and responds to commands. Another Actor might coordinate a measurement sequence across several devices.

Today, the [linear-slide deployment](examples/slide_nodes/README.md) implements this coordination with services, apps, and signals on explicitly configured logical nodes. It is a working foundation for the model, not an implementation of relocatable Actors.

Moving computation cannot reconnect a motor wired to a failed board. Alternative placement requires compatible resources and access to the required capabilities. Stateless restart comes first; stateful recovery requires previously saved or replicated state. Power and thermal policies must account for both computation and local hardware loads.

## Architecture

The existing package boundaries remain useful:

| Responsibility | Current location |
| --- | --- |
| Capability contracts and portable support | `PrimitiveFabric/foundation/` |
| Assembly, lifecycle, operations, workflows, signals, discovery | `PrimitiveFabric/runtime/` |
| Network adapters | `PrimitiveFabric/transports/` |
| HTTP and shell controls | `PrimitiveFabric/control/` |
| Boot and environment facilities | `PrimitiveFabric/platform/` |
| Telemetry | `PrimitiveFabric/observability/` |
| Capability providers, drivers, adapters, composites | `PrimitiveFabric/services/` |
| Application orchestration | `PrimitiveFabric/apps/` |
| Current manifest schemas | `PrimitiveFabric/spec/` |
| Device deployments and host simulations | `examples/` |

Fabric management is a proposed responsibility spanning placement, ownership, recovery, and deployment reconciliation. It builds on these layers rather than replacing capability contracts or device ownership.

The related StepperNode / Steppin Cube hardware project is one possible building block for deployments. Somatic Mesh is the framework; it is not the name of that controller or a claim that its intended hardware capabilities have all been validated.

## Explore the implementation

Start with the [getting-started guide](docs/content/getting-started.md), the [Robie1 host simulation](examples/robie1/README.md), or the [linear-slide test app](examples/linear_slide/README.md). Follow [multiple-device deployment](docs/content/deployment.md) to run the slide and its client on separate boards.

Packages remain independently installable through their existing manifests. For example, from the repository root:

```sh
mpremote mip install PrimitiveFabric/services/distance_sensor/package.json
```

The installed namespace remains `rpstack.<component>`. Preserve device-specific settings when reinstalling and use exact, compatible package revisions for repeatable deployments.

## Documentation and validation

- [Documentation overview](docs/content/index.md): product model and implementation guides.
- [Mental model](docs/content/concepts.md): Actors, Behaviors, Devices, and current runtime terminology.
- [Architecture](PrimitiveFabric/ARCHITECTURE.md): layers, boundaries, and implementation mapping.
- [Fabric management](docs/content/fabric-management.md): placement, authority, recovery, and development sequence.
- [Documentation build](docs/README.md): rebuild and preview the committed site.
- [Current implementation reference](CURRENT_IMPLEMENTATION.md): detailed runtime, service, and manifest examples.
- [Service manifest reference](PrimitiveFabric/spec/SERVICE_MANIFEST.md): current contracts and schema.

Use `python3 tools/check_architecture.py` for package-map and isolated-installation checks and `python3 tools/run_tests.py` for host regression suites. Device timing, physical feedback, memory use, and radio behavior need hardware validation.
