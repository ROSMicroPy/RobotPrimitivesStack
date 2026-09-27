# Somatic Mesh

**A distributed compute framework and management system for small devices.**

*Design in The Loom. Bring Actors and Behaviors to life across the Fabric.*

Somatic Mesh connects small devices into coordinated systems. Its intended model assigns Behaviors to Actors and deploys them across a Fabric of suitable runtime hosts. The framework manages execution, communication, and software deployment, with a roadmap for recovery and resource-aware placement.

## Where the project stands

The current implementation is RPStack: manifest-driven logical nodes, reusable capability services, supervised operations, apps, workflows, signals, transports, and discovery. **Actors as a stable runtime abstraction, automatic placement, and recovery on alternative hosts are proposed work.** Current packages, schemas, commands, and examples retain their RPStack names.

The Loom is the proposed name for the Robot Architect authoring and management environment. ILA (Intelligent Loom Assistant) is its proposed assistant. Deployed operation and permitted recovery should be independent of the desktop and internet.

## Understand the model

- [Actors, Behaviors, and the Fabric](concepts.html): product concepts and their relationship to current APIs.
- [Architecture](architecture.html): existing package boundaries and proposed management responsibilities.
- [Fabric management and recovery](fabric-management.html): placement, ownership, recovery limits, and development sequence.
- [Nodes and manifests](nodes.html): the supported deployment format and its planned separation into application, hardware, and placement descriptions.

## Run what exists today

Start with a host simulation, then install the linear-slide example on an ESP32. Its signal-driven client can run beside the slide service or on a second device. These demonstrate current fixed deployment and capability coordination.

- [Getting started](getting-started.html): simulation and first-device installation.
- [Multiple devices](deployment.html): explicit placement and transport setup.
- [Apps and Behaviors](apps.html): current app and workflow implementation patterns.
- [Linear slide](linear-slide.html) and [API reference](api.html): calibration, operations, and tracked tasks.
- [ROS 2 integration](ros-integration.html): typed telemetry and the slide action gateway.

## Plan the management layer

[Provisioning and bootstrap](bootstrap.html) proposes identity provisioning, software delivery through The Loom, readiness, and onboard run permission. [Software registries](registries.html) proposes exact version resolution and deployment locks. Both remain designs rather than current installation guarantees.

Somatic Mesh is independent of a specific board or transport. The related StepperNode / Steppin Cube hardware is a potential building block, not the framework itself.
