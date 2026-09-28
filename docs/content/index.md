# Somatic Mesh

**A distributed compute framework and management system for small devices.**

*Design in The Loom. Bring Actors and Behaviors to life across the Fabric.*

Somatic Mesh coordinates small devices through Actors and Behaviors. A Fabric Node hosts Actors, provides capability services, and manages operations, workflows, and communication. The Loom authors and observes the system; deployed local sequences run independently of its connection.

ROSMicroPy provides the embedded ROS foundation. ROS interfaces connect the Fabric to robots and other ROS participants. ESP-NOW lets local devices cooperate without an access point or IP configuration, with bounded relaying for configured mesh deployments.

## Understand the system

- [Mental model](concepts.html): Actors, Behaviors, Devices, capabilities, and tasks.
- [Actors and Behaviors](actors.html): implement a Behavior and assign it to an Actor.
- [Architecture](architecture.html): package responsibilities and dependency boundaries.
- [Nodes and manifests](nodes.html): configure resources, services, Actors, workflows, and transports.

## Run a deployment

- [Getting started](getting-started.html): host simulation and first-device installation.
- [Multiple devices](deployment.html): explicit placement and ESP-NOW configuration.
- [Linear slide](linear-slide.html) and [API reference](api.html): calibration, commands, and tracked outcomes.
- [ROS integration](ros-integration.html): ROSMicroPy telemetry and the typed slide action gateway.

## Management roadmap

[Fabric management](fabric-management.html), [bootstrap](bootstrap.html), and [software registries](registries.html) specify planned placement, inventory, readiness, code delivery, and recovery responsibilities. They are design documents; automatic Actor relocation and stateful recovery are not runtime features.

Somatic Mesh is independent of a particular controller board. StepperNode / Steppin Cube is a related hardware building block for instrumented deployments.
