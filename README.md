# Robot Primitives Software Stack

Robot Primitives Software Stack, or **RPStack**, is a framework for building modular robotic devices from small, reusable capabilities.

A device is assembled from services such as a motor controller, distance sensor, position observer, camera, gripper, or linear actuator. Each service describes itself through a manifest. The Node Runtime reads those manifests, connects compatible services, starts them in dependency order, exposes their supported operations, and manages their lifecycle.

RPStack is designed for constrained embedded systems, especially MicroPython targets, while keeping the same architectural model usable in host simulations, test tools, ROS 2 bridges, and web interfaces.

## Documentation

The [documentation site](docs/README.md) covers getting started, nodes, signals, apps, runtime and services, deployment, and the linear-slide APIs. Source pages live in `docs/content/`; build and preview instructions are in `docs/README.md`.

The [architecture guide](RPStack/ARCHITECTURE.md) describes package responsibilities, dependency boundaries, and terminology.

## Run the manifest-driven test node

The [linear slide test app](examples/linear_slide/README.md) boots from one
`rp.node/v1` manifest. It declares hardware resources, service instances, driver
choices, runtime listeners, and optional signal-driven workflows. The generic
boot entry only calls `run_manifest(path)`.

All node services run as tracked asyncio tasks. The console's `ps` lists them;
HTTP operations return task IDs. Stop/reset remain available during motion and
signal waits. See the [node schema](RPStack/spec/node-manifest.schema.json) and
[execution engine](RPStack/runtime/execution_engine/README.md). Runtime API examples
below use `await` inside an async application entry point.

## Robot-wide signals

[Entity-scoped signals](RPStack/runtime/signals/README.md) connect local tasks,
[ESP-NOW mesh](RPStack/transports/espnow/README.md), and
[ROS messaging](RPStack/transports/ros_signals/README.md). Manifest workflows can
coordinate actions across nodes of one robot. Run the three-node
[Robie1 simulation](examples/robie1/README.md) without hardware to explore it.

## The basic idea

A robotic device is described through four conceptual layers. These explain responsibilities; they are not strict Python import tiers:

1. **Platform** supplies the firmware and low-level hardware environment.
2. **Node Runtime** discovers, connects, starts, monitors, and stops services.
3. **Services** expose reusable hardware-independent capabilities.
4. **Applications and workflows** coordinate those capabilities into useful robot behavior.

Bridges connect the internal RPStack model to external systems such as ROS 2 and ESP-NOW; HTTP and the shell expose node controls.

~~~mermaid
flowchart TB
    BG["Applications and workflows"]
    PS["Services"]
    PR["Node Runtime"]
    DP["Platform"]

    BG --> PS
    PS --> PR
    PR --> DP
~~~

The repository groups separate these responsibilities further so transports, control interfaces, platform helpers, and telemetry remain independently installable. See the [architecture guide](RPStack/ARCHITECTURE.md) for package boundaries and terminology.

A helpful way to think about these layers is:

| Layer | Question it answers |
|---|---|
| Device Platform | What can this hardware run? |
| Node Runtime | How are services assembled and managed? |
| Primitive Services | What can this device do? |
| Applications and workflows | What should the device do next? |
| Bridges | How does the device communicate with other systems? |

## A first example

Consider a stepper-driven linear slide with a time-of-flight distance sensor.

The system contains four services:

| Service | Responsibility | Capability |
|---|---|---|
| Stepper motor | Produces incremental motion | motion.motion_actuator |
| ToF sensor | Measures distance along its sensing ray | sensing.distance_observer |
| Distance-to-position adapter | Converts distance into installed carriage position | motion.position_observer |
| Linear-slide composite | Coordinates motion and feedback | motion.position_actuator |

~~~mermaid
flowchart TB
    APP["Behavior or application"]
    SLIDE["Linear slide composite"]
    MOTOR["Stepper motor"]
    POSITION["Distance-to-position adapter"]
    TOF["ToF distance sensor"]

    APP -->|"move_to(target)"| SLIDE
    SLIDE --> MOTOR
    SLIDE --> POSITION
    POSITION --> TOF
~~~

The linear-slide service knows how to reach a target, enforce travel limits, stop on failure, and determine when motion is complete. It does not need to know which stepper controller or position sensor was selected. It depends on capability interfaces and receives matching service instances from the runtime.

This separation makes it possible to replace the ToF sensor with a linear encoder, use a simulated motor in a test, or expose a remote motion capability through a bridge without rewriting the composite service.

## Repository layout

All stack components live under the **RPStack** directory.

~~~text
RPStack/
├── foundation/{interfaces,support}/
├── runtime/{node_runtime,execution_engine,signals,catalog}/
├── transports/{espnow,ros_signals}/
├── control/{http,shell}/
├── platform/{bootmgr,env}/
├── observability/opentelemetry/
├── services/{distance_sensor,distance_to_position,motor_control,linear_slide}/
├── apps/{robot_gateway,slide_commands}/
└── spec/
examples/                  # Device deployments and host simulations
RPStack_WebTester/         # Web client submodule
~~~

The top-level **RPStack_WebTester** entry is a Git submodule containing a dynamic web-form client. It demonstrates form rendering for service interaction. Operation and test descriptions in each service manifest provide the data model for manifest-driven interfaces.

## Layer 1: Platform

The Device Platform is the compiled firmware environment installed on a board. It provides the facilities required by the runtime and services.

Typical platform contents include:

- MicroPython
- board support and pin definitions
- native C or C++ drivers
- an RTOS or hardware abstraction layer
- ROSMicroPy
- ESP-NOW networking
- observability support
- networking, storage, and device-specific extensions

A platform image is normally associated with a hardware family:

~~~text
rp-platform-esp32s3-v1.4.0.bin
rp-platform-esp32p4-v1.4.0.bin
rp-platform-nrf9151-v1.4.0.bin
~~~

The platform provides the execution environment. Installed services and device configuration determine the capabilities of a particular node.

## Layer 2: Runtime

The Node Runtime is the common service-management layer. Its core implementation is under:

~~~text
RPStack/runtime/node_runtime/
~~~

The runtime provides:

- service-manifest loading and structural validation
- capability registration
- interface-version matching
- semantic constraint matching
- automatic and explicit dependency binding
- dependency-cycle detection
- deterministic startup ordering
- reverse-order shutdown
- lifecycle failure handling
- allowlisted operation invocation
- implementation-specific operation checks
- declarative service-test execution

Additional runtime packages provide boot orchestration, environment storage, shell access, and OpenTelemetry support.

### Runtime flow

A device application registers the service instances it wants to run. Each registration supplies a manifest and a factory that can construct the service.

The runtime then performs these steps:

~~~mermaid
flowchart TB
    REGISTER["Register service definitions"]
    RESOLVE["Resolve capability requirements"]
    ORDER["Build dependency order"]
    CREATE["Construct service instances"]
    CONFIGURE["Configure and initialize"]
    START["Start providers before consumers"]
    OPERATE["Invoke declared operations"]
    STOP["Stop consumers before providers"]

    REGISTER --> RESOLVE
    RESOLVE --> ORDER
    ORDER --> CREATE
    CREATE --> CONFIGURE
    CONFIGURE --> START
    START --> OPERATE
    OPERATE --> STOP
~~~

If startup fails after some services are running, the supervisor stops the services that were already started. Normal shutdown uses reverse dependency order so a composite is stopped before the motor and sensor services it uses.

### Runtime registration

The following example shows the shape of a device assembly:

~~~python
from rpstack.node_runtime import ServiceManifest, ServiceSupervisor

runtime = ServiceSupervisor()

motor_manifest = ServiceManifest.load(
    "services/motor_control/component.yaml"
)
position_manifest = ServiceManifest.load(
    "services/distance_to_position/component.yaml"
)
slide_manifest = ServiceManifest.load(
    "services/linear_slide/component.yaml"
)

runtime.register(
    "lift_motor",
    motor_manifest,
    factory=make_lift_motor,
    implementation="step_dir",
)

runtime.register(
    "lift_position",
    position_manifest,
    factory=make_lift_position,
    bindings={"distance_observer": "lift_tof"},
)

runtime.register(
    "lift",
    slide_manifest,
    factory=LinearSlide,
    bindings={
        "motor": "lift_motor",
        "position": "lift_position",
    },
    config={
        "tolerance_m": 0.001,
        "max_steps": 10000,
    },
)

await runtime.start()
await runtime.invoke("lift", "move_to", {"target": 0.100})
await runtime.stop()
~~~

Factories are responsible for supplying platform resources such as I2C buses, GPIO pins, timers, and concrete driver instances. The runtime is responsible for capability binding and lifecycle management.

### Automatic and explicit binding

A required capability is identified by a role name, interface, version, and optional constraints.

~~~yaml
requires:
  motor:
    interface: motion.motion_actuator
    version: 1
    constraints:
      mode: incremental

  position:
    interface: motion.position_observer
    version: 1
    constraints:
      quantity: linear
      dimensions: 1
      canonical_unit: m
~~~

The runtime can bind a role automatically when exactly one registered provider matches.

An explicit binding is used when:

- more than one compatible provider exists;
- a specific physical device must fill the role;
- two identical composites use different motors or sensors;
- predictable wiring is more important than automatic selection.

~~~python
bindings={
    "motor": "lift_motor",
    "position": "lift_position",
}
~~~

The runtime reports an error if no provider matches, a binding is incompatible, multiple providers are ambiguous, or the dependency graph contains a cycle.

## Layer 3: Services

A Primitive Service is the unit managed by the runtime. Every service has:

- an identity and version;
- a service kind and type;
- a lifecycle;
- zero or more provided capabilities;
- zero or more required capabilities;
- configuration fields;
- declared operations;
- signals;
- implementation choices;
- declarative tests.

RPStack uses three main service kinds.

### Individual drivers

An individual driver controls or observes one independently addressable component.

Examples include:

- a STEP/DIR motor driver;
- a PWM servo;
- a VL53L4CD ToF sensor;
- a rotary encoder;
- an IMU;
- a camera.

An individual driver owns the hardware protocol and device-specific configuration. It should not contain assumptions about the larger mechanism where the component is installed.

Concrete drivers live inside their service package. For example, **motor_control** contains its STEP/DIR, PWM servo, and PWM BLDC implementations. The package exposes a consistent service API while allowing the manifest to identify the selected implementation and its configuration.

### Adapters

An adapter converts one capability or representation into another.

The included **distance_to_position** adapter consumes a raw distance observation and provides a linear position observation. It owns installation-specific information such as:

- zero offset;
- measurement direction;
- reference frame;
- usable range;
- inversion;
- calibration.

A ToF sensor measures distance along a ray. It does not inherently know that the result represents the position of a carriage. Keeping that interpretation in an adapter makes the sensor driver reusable.

### Composite drivers

A composite driver coordinates two or more capabilities and exposes a higher-level capability.

The included **linear_slide** composite requires:

- an incremental motion actuator in the **motor** role;
- a one-dimensional linear position observer in the **position** role.

It provides a position-actuator capability with operations such as **move_to** and **stop**.

Composite services own mechanism-level behavior, including:

- target validation;
- completion tolerance;
- homing policy;
- approach direction;
- motion timeout;
- stall detection;
- limit handling;
- coordinated safe state.

A runtime-bound composite does not own the lifecycle of its dependencies. Stopping the composite can stop motion, while the supervisor remains responsible for shutting down the shared motor and sensor services.

## Capability interfaces

A capability interface describes what a service can do without naming a hardware model or package.

Capability contracts are defined in:

~~~text
RPStack/foundation/interfaces/
~~~

The initial interface set includes:

| Interface | Purpose |
|---|---|
| sensing.distance_observer | Returns distance along a sensing ray |
| motion.position_observer | Returns linear or angular position |
| motion.motion_actuator | Commands relative motion and stop |
| motion.position_actuator | Commands an absolute target position and stop |

An interface identifier has an independent major version:

~~~yaml
interface: motion.position_observer
version: 1
~~~

The major version is part of dependency matching. Additional fields describe the meaning of the capability:

~~~yaml
- interface: motion.position_observer
  version: 1
  quantity: linear
  dimensions: 1
  canonical_unit: m
~~~

These fields prevent a one-dimensional linear actuator from binding to an angular observer merely because both expose position data.

## Measurements and units

Measurements carry enough information to be interpreted outside the driver that produced them.

A position sample includes:

~~~python
PositionSample(
    kind="linear",
    value=0.100,
    unit="m",
    reference_frame="lift.base",
    timestamp_ns=None,
    valid=True,
    quality=1.0,
)
~~~

Standard fields include:

| Field | Meaning |
|---|---|
| value | Numeric measurement in canonical units |
| unit | Unit associated with the value |
| timestamp_ns | Acquisition time when available |
| valid | Whether the measurement can be used |
| quality | Normalized confidence from 0.0 to 1.0 |
| reference_frame | Coordinate or installation frame |
| kind | Linear or angular for position samples |

Capability boundaries use SI units:

- linear position: metres
- angular position: radians
- linear velocity: metres per second
- angular velocity: radians per second

Drivers may use native units internally. Conversion occurs before data crosses the capability interface; services exchange canonical measurement samples.

## Service lifecycle

Every runtime-managed service can map the following lifecycle stages to its implementation methods:

~~~text
configure → init → start → stop
                    ↘ reset
                    ↘ status
~~~

| Stage | Responsibility |
|---|---|
| configure | Accept instance configuration |
| init | Allocate or initialize resources |
| start | Enter the operational state |
| stop | Enter a safe non-operating state |
| reset | Recover or reinitialize the service |
| status | Return health and operating information |

Lifecycle names in the manifest are mappings. A service can use different internal method names if its manifest maps them correctly.

Functional interfaces and lifecycle interfaces are separate. For example, a motor service implements lifecycle methods for the supervisor and motion methods for consumers.

## The service manifest

Every service package contains a **component.yaml** file. This file is the canonical **rp.service/v1** manifest.

The manifest is a generic specification used by:

- the Node Runtime;
- host-side validation;
- device assembly tools;
- CLI and debugging tools;
- REST or WebSocket bridges;
- generated operation forms;
- generated test forms;
- documentation tools.

The complete schema is available at:

~~~text
RPStack/spec/service-manifest.schema.json
~~~

A detailed format description is available at:

~~~text
RPStack/spec/SERVICE_MANIFEST.md
~~~

### Manifest structure

A manifest begins with its schema identifier, package information, and service definition:

~~~yaml
manifest: rp.service/v1

package:
  name: distance-to-position
  version: 0.1.0
  import: rpstack.distance_to_position

service:
  name: distance-to-position
  version: 0.1.0
  kind: adapter
  type: adapter.distance_to_position
  description: Convert a ray distance into installed linear position.
  entry_point: rpstack.distance_to_position:DistanceToPositionAdapter
~~~

The remaining service sections describe capabilities, configuration, lifecycle, operations, signals, implementations, and tests.

### Capabilities

**provides** lists the interfaces a service makes available. **requires** maps constructor roles to the capabilities the service consumes.

~~~yaml
capabilities:
  provides:
    - interface: motion.position_observer
      version: 1
      quantity: linear
      dimensions: 1
      canonical_unit: m

  requires:
    distance_observer:
      interface: sensing.distance_observer
      version: 1
~~~

The role name is significant. A bound provider for **distance_observer** is passed to a factory or constructor using that keyword.

### Configuration

Configuration descriptions are data schemas that can be validated or rendered as forms.

~~~yaml
configuration:
  zero_offset_m:
    type: number
    default: 0.0
    unit: m

  direction:
    type: integer
    enum: [-1, 1]
    default: 1

  reference_frame:
    type: string
    required: true
~~~

Hardware implementations can add their own configuration. The motor-control manifest, for example, places **step_pin**, **dir_pin**, and timing parameters under the **step_dir** implementation.

### Lifecycle

The lifecycle section maps runtime stages to service methods:

~~~yaml
lifecycle:
  configure: configure
  init: init
  start: start
  stop: stop
  reset: reset
  status: status
~~~

An omitted stage requires no runtime call.

### Operations

Operations are the public, remotely invokable surface of a service.

~~~yaml
operations:
  move_to:
    method: move_to
    description: Move the carriage to an absolute linear position.
    arguments:
      target:
        type: number
        required: true
        unit: m
    returns:
      type: PositionSample
      quantity: linear
      unit: m
    concurrency: exclusive
    cancellable: true
    safe_state: stop
~~~

Only declared operations can be invoked through **ServiceSupervisor.invoke**. Arguments not declared by the operation are rejected, and required arguments must be present.

Operation metadata can describe:

- argument types, units, defaults, and ranges;
- return data;
- read-only or exclusive concurrency;
- cancellation support;
- idempotency;
- errors;
- the safe-state operation;
- which concrete implementations support the operation.

This section supplies the information needed to generate a CLI command or web form without embedding service-specific UI logic.

### Concrete implementations

A service package can contain multiple hardware implementations:

~~~yaml
implementations:
  step_dir:
    entry_point: rpstack.motor_control.motor_drivers.step_dir:StepDirDriver
    description: Incremental STEP/DIR motor controller.
    capabilities:
      provides:
        - interface: motion.motion_actuator
          version: 1
          mode: incremental
      requires: {}
    configuration:
      step_pin: {type: pin_ref, required: true}
      dir_pin: {type: pin_ref, required: true}
      enable_pin: {type: pin_ref, required: false}
    safe_state: stop
~~~

Implementation-level capabilities let the runtime distinguish between variants in the same package. Selecting **step_dir** adds its incremental motion capability to the registered motor service.

### Signals

Signals describe events or state updates emitted and consumed by a service.

~~~yaml
signals:
  provides:
    motion.position.updated:
      payload: PositionSample
    motion.target.reached:
      payload: PositionSample

  consumes: {}
~~~

Signals are transport-independent. A signal can remain local, cross Lighthouse Mesh, become a ROS 2 message, or be presented over a network bridge without changing the service that emitted it.

### Declarative tests

Tests describe how to exercise a service through its declared operations.

~~~yaml
tests:
  observe_position:
    description: Read the current carriage position without moving it.
    mode: automatic
    steps:
      - operation: observe_position
        arguments: {}
        expect:
          fields:
            kind: linear
            unit: m
            valid: true
~~~

Three modes are available:

| Mode | Intended use |
|---|---|
| automatic | Safe to run without operator approval |
| manual | Requires an explicit request |
| hardware | May move or energize hardware and requires explicit approval |

A hardware test can declare preconditions and operator-provided parameters:

~~~yaml
move_to_target:
  description: Move to an operator-selected target.
  mode: hardware
  preconditions:
    - Verify physical clearance.
    - Ensure emergency power removal is available.
  parameters:
    target:
      type: number
      required: true
      unit: m
  steps:
    - operation: move_to
      arguments:
        target:
          $parameter: target
~~~

The test runner refuses to execute manual or hardware tests unless approval is supplied. Test steps can assert an exact return value or selected fields in a returned object or measurement sample.

~~~python
from rpstack.node_runtime import ManifestTestRunner

runner = ManifestTestRunner(runtime)

result = await runner.run(
    "lift",
    "move_to_target",
    parameters={"target": 0.100},
    allow_manual=True,
)
~~~

## Operating a service

Applications invoke services through operation names from the manifest:

~~~python
sample = await runtime.invoke("lift", "observe_position")

final_position = await runtime.invoke(
    "lift",
    "move_to",
    {"target": 0.100},
)

await runtime.invoke("lift", "stop")
~~~

This operation layer provides a stable boundary for local code, CLI commands, WebTester forms, REST endpoints, and bridge implementations.

Code running inside a composite service can call its injected capability objects directly. External tools should use declared operations so that validation, safety metadata, and implementation restrictions remain available.

## Manifest formats on host and device

YAML is the human-authored format. It is readable, supports comments, and is convenient for review.

Stock MicroPython includes JSON support but generally does not include a YAML parser. The runtime therefore accepts both formats:

- **component.yaml** for development and host tooling;
- generated compact JSON for deployment to constrained devices.

Generate a device JSON manifest with:

~~~bash
python RPStack/runtime/node_runtime/tools/compile_manifest.py     RPStack/services/linear_slide/component.yaml     linear_slide.component.json
~~~

The compiler loads and validates the YAML through the same manifest model used by the runtime before writing compact JSON.

## Signals, actions, and operations

RPStack distinguishes three related concepts.

### Operations

An operation is a direct request to one service and normally returns a result.

Examples:

~~~text
observe_distance
move_to
stop
status
~~~

### Signals

A signal reports an event or state change.

Examples:

~~~text
range.distance.updated
motion.position.updated
motion.target.reached
device.health.changed
~~~

### Actions

At the behavior level, an action represents an intended operation, including any timeout, cancellation, retry, or completion policy. A behavior engine can translate an action into a service operation and wait for the corresponding signals.

Hierarchical names use this pattern:

~~~text
domain.component.event
~~~

The signal name and source identity remain separate:

~~~yaml
source: robot.arm.left.shoulder
signal: motion.target.reached
~~~

## Bridges

A bridge adapts RPStack capabilities, operations, and signals to an external transport.

Possible bridges include:

- ROS 2
- ESP-NOW networking
- REST
- WebSocket
- MQTT

~~~mermaid
flowchart LR
    SERVICE["Primitive Service"]
    RUNTIME["Node Runtime"]
    BRIDGE["Bridge"]
    EXTERNAL["External system"]

    SERVICE <--> RUNTIME
    RUNTIME <--> BRIDGE
    BRIDGE <--> EXTERNAL
~~~

A bridge owns transport-specific concepts such as ROS messages, HTTP routes, or mesh packets. Primitive Services remain focused on their capabilities and do not require transport-specific code.

## Layer 4: Applications and workflows

Applications and workflows coordinate service operations and signals into robot behavior.

The following list describes the broader behavior model. The current workflow engine supports operation/signal steps and success/error transitions; general parallel branches and retry policies remain design goals.

A behavior can describe:

- triggers and conditions;
- operation requests;
- sequencing;
- parallel work;
- state transitions;
- completion signals;
- timeouts;
- cancellation;
- retries;
- error handling.

For example, a behavior might react to an object detector, close a gripper, and move a linear slide after the grip completes.

~~~mermaid
flowchart LR
    DETECT["Object detected"]
    MATCH{"Target class?"}
    GRIP["Close gripper"]
    MOVE["Move slide"]
    DONE["Complete"]

    DETECT --> MATCH
    MATCH -->|"match"| GRIP
    GRIP -->|"grip complete"| MOVE
    MOVE -->|"target reached"| DONE
~~~

Behavior definitions operate on service identities, operation names, and signal names. They do not need to know the concrete motor or sensor models fulfilling each capability.

## Building a device

A deployed node consists of:

~~~text
Device Platform
+ Node Runtime
+ Primitive Service packages
+ device-specific service registration and configuration
+ optional Behavior Definitions
+ optional Bridges
~~~

The same firmware image can support different devices by installing different services and changing their configuration and bindings.

A device assembly normally identifies:

- each service instance;
- the selected service package;
- the selected concrete implementation;
- hardware resources;
- service configuration;
- explicit capability bindings where needed;
- behaviors and bridges to start.

## Component directory layout

Each independently installable package in the responsibility groups above uses this structure:

~~~text
component/
├── README.md
├── package.json
├── src/
└── test/
~~~

Importable and startup code lives under `src/`; host tests and hardware-test guidance live under `test/`. Services also contain `component.yaml`, the generic runtime, operation, and testing specification. Optional `examples/` and `tools/` directories contain development resources. Each MIP manifest maps files from `src/` to their installed device paths.

## Adding a service

Use the following workflow when adding an individual driver, adapter, or composite.

1. Create a directory under **RPStack/services**.
2. Implement the service lifecycle.
3. Implement or consume capability interfaces from **foundation/interfaces**.
4. Keep hardware-model code under the service package implementation directory.
5. Add a canonical **component.yaml** manifest.
6. Declare configuration, capabilities, operations, signals, and tests.
7. Add a MicroPython **package.json** when the service is deployable through mip.
8. Add host tests with fake capabilities or fake hardware.
9. Validate that composites can be constructed through runtime role binding.
10. Mark any test that moves or energizes hardware as **hardware**.

A service manifest should be complete enough that a reader or tool can answer:

- What does this service provide?
- What does it require?
- How is it configured?
- How is it started and stopped?
- Which operations are safe to expose?
- What does each operation accept and return?
- What signals can appear?
- Which concrete implementations are available?
- How can the service be tested safely?

## Testing the stack

Run the Node Runtime tests from the repository root:

~~~bash
python -m unittest discover     -s RPStack/runtime/node_runtime/test     -v
~~~

Run the linear-slide service tests:

~~~bash
python -m unittest discover     -s RPStack/services/linear_slide/test     -v
~~~

Compile Python sources:

~~~bash
python -m compileall -q     RPStack/runtime/node_runtime/src     RPStack/services
~~~

Validate and compile an individual manifest:

~~~bash
python RPStack/runtime/node_runtime/tools/compile_manifest.py     RPStack/services/distance_sensor/component.yaml     distance_sensor.component.json
~~~

Host tests use fake hardware and capability implementations. Tests that require physical motion remain declared in the manifest and must be run with explicit operator approval.

## Included services

### RPInterfaces

Defines the common lifecycle, measurement, observer, and actuator contracts. The implementation avoids CPython-only abstractions so it can run on MicroPython.

### DistanceSensor

Provides a scalar distance-observer capability. Included hardware implementations support HCSR04 ultrasonic sensors and VL53L4CD time-of-flight sensors.

### DistanceToPosition

Consumes a distance observer and provides a one-dimensional linear position observer using installation calibration and a reference frame.

### MotorControl

Provides reusable motor services with STEP/DIR, PWM servo, and PWM BLDC implementations. The selected implementation determines the capabilities and operations available to the instance.

### LinearSlide

Combines an incremental motion actuator and a linear position observer into a closed-loop position actuator. It exposes SI-based capability operations and millimetre convenience operations.

## Package installation

Every runtime and service component is an independent MIP package whose file sources are relative to its own `package.json`. The installed Python namespace is `rpstack.<component>` on both host and device.

Use an explicit manifest path for local installation:

~~~bash
# From a component directory
mpremote mip install ./package.json

# From the repository root
mpremote mip install RPStack/services/distance_sensor/package.json
~~~

Use MicroPython's GitHub shorthand or a raw manifest URL for repository installation:

~~~bash
mpremote mip install github:ROSMicroPy/RobotPrimitivesStack/RPStack/services/distance_sensor@archdef
mpremote mip install https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/archdef/RPStack/services/distance_sensor/package.json
~~~

Local directory names are not package arguments in the current `mpremote mip` implementation, so `mpremote mip install .` and a directory-only local path do not resolve `package.json` automatically.


Service and runtime packages include MicroPython **package.json** files where applicable. A package manifest specifies installed files and dependent RPStack packages.

For example, the linear-slide package depends on:

- RPInterfaces
- MotorControl
- DistanceSensor
- DistanceToPosition

During development on **archdef**, package dependencies reference that branch. Release packaging should use an immutable release tag so every installed dependency resolves to a consistent stack version.

## Design principles

RPStack follows these principles:

1. Firmware supplies a reusable hardware execution environment.
2. Services describe device capabilities.
3. Capability interfaces are independent of hardware models.
4. Runtime bindings target interfaces and semantic constraints.
5. Raw sensor meaning is preserved until an adapter adds installation meaning.
6. Composite services own mechanism behavior and safety policy.
7. Capability boundaries use explicit units and reference frames.
8. Manifests are the single source for runtime, operation, and test metadata.
9. Only declared operations are exposed through generic tooling.
10. Hardware tests require explicit operator approval.
11. Signals remain independent of their transport.
12. Bridges contain protocol-specific integration.
13. Behaviors coordinate services without depending on concrete drivers.

## Further reference

- **Manifest guide:** RPStack/spec/SERVICE_MANIFEST.md
- **Manifest JSON Schema:** RPStack/spec/service-manifest.schema.json
- **Node Runtime:** RPStack/runtime/node_runtime/
- **Capability interfaces:** RPStack/foundation/interfaces/
- **Linear-slide example:** RPStack/services/linear_slide/

## Node applications and robot discovery

[Node apps](RPStack/apps/README.md) orchestrate services through the runtime.
Multiple apps can run concurrently on one node. The
[catalog](RPStack/runtime/catalog/README.md) discovers robot-wide node profiles,
and the [robot gateway](RPStack/apps/robot_gateway/README.md) exposes them over HTTP.

The linear-slide deployment includes the gateway; a standalone
[gateway node](examples/mesh_gateway/README.md) is also provided. Enable catalog
and network signal routes on every participating node.
