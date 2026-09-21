# PrimitiveRuntime

PrimitiveRuntime loads RPStack service manifests, binds compatible capabilities, manages service lifecycle, exposes declared operations, and executes declarative tests.

The package is designed for MicroPython and host-side simulation.

## Main classes

| Class | Responsibility |
|---|---|
| ServiceManifest | Load and validate rp.service/v1 manifests |
| ServiceDefinition | Hold one registered service instance definition |
| CapabilityRegistry | Match requirements to providers and order dependencies |
| ServiceSupervisor | Construct, configure, start, invoke, restart, and stop services |
| ManifestTestRunner | Execute tests declared by a service manifest |

## Loading manifests

~~~python
from PrimitiveRuntime import ServiceManifest

slide_manifest = ServiceManifest.load(
    "RPStack/services/linear_slide/component.yaml"
)
~~~

YAML requires a compatible **yaml.safe_load** implementation. JSON works with the standard MicroPython JSON module.

Generate compact device JSON with:

~~~bash
python tools/compile_manifest.py     ../../services/linear_slide/component.yaml     linear_slide.component.json
~~~

## Registering services

~~~python
from PrimitiveRuntime import ServiceSupervisor

runtime = ServiceSupervisor()

runtime.register(
    "motor",
    motor_manifest,
    factory=make_motor,
    implementation="step_dir",
)

runtime.register(
    "position",
    position_manifest,
    factory=make_position,
)

runtime.register(
    "slide",
    slide_manifest,
    factory=LinearSlide,
    bindings={"motor": "motor", "position": "position"},
    config={"tolerance_m": 0.001},
)
~~~

A registration contains:

| Field | Meaning |
|---|---|
| service_id | Unique device-local instance name |
| manifest | ServiceManifest or manifest dictionary |
| factory | Callable that constructs the instance |
| implementation | Selected concrete implementation |
| bindings | Explicit role-to-service mappings |
| config | Values passed to the configure lifecycle stage |

Factories receive resolved dependency roles as keyword arguments. Platform-specific factories can also close over GPIO, I2C, SPI, timers, or concrete driver objects.

## Dependency resolution

**prepare()** resolves every required capability.

A provider matches when:

- the interface identifier matches;
- the major interface version matches;
- every required semantic constraint matches.

Automatic selection requires exactly one provider. Explicit bindings select a provider by service ID. Missing providers, incompatible bindings, ambiguous providers, and cycles raise **ResolutionError**.

~~~python
order = runtime.prepare()
~~~

The returned list is the dependency order used for construction and startup.

## Lifecycle

~~~python
runtime.start()
runtime.restart("slide")
status = runtime.status("slide")
runtime.stop()
~~~

The supervisor uses lifecycle method mappings from each manifest.

During preparation it:

1. constructs providers before consumers;
2. passes dependency instances to consumer factories;
3. calls configure;
4. calls init.

During startup it calls start in dependency order. Shutdown calls stop in reverse order. A startup failure stops services that already entered the running state.

## Operations

~~~python
position = runtime.invoke("slide", "observe_position")

result = runtime.invoke(
    "slide",
    "move_to",
    {"target": 0.100},
)
~~~

The supervisor permits only operations declared by the manifest. It rejects undeclared arguments, missing required arguments, and operations unavailable for the selected implementation.

## Declarative tests

~~~python
from PrimitiveRuntime import ManifestTestRunner

runner = ManifestTestRunner(runtime)

safe_result = runner.run("slide", "observe_position")

motion_result = runner.run(
    "slide",
    "move_to_target",
    parameters={"target": 0.100},
    allow_manual=True,
)
~~~

Automatic tests run without an approval flag. Manual and hardware tests require **allow_manual=True**. Test parameters are substituted into step arguments, and expectations can compare exact results or selected fields.

## Exceptions

| Exception | Meaning |
|---|---|
| ManifestError | Invalid document, operation, test, or entry point |
| ResolutionError | Missing, ambiguous, incompatible, or cyclic dependency |
| LifecycleError | Lifecycle or operation invocation failure |
| ManifestTestError | Test approval, parameter, or expectation failure |

## Installation

Install the package through its **package.json**. It places the runtime modules under **PrimitiveRuntime/**.

## Tests

From the repository root:

~~~bash
python -m unittest discover     -s RPStack/runtime/primitive_runtime/tests     -v
~~~

The tests cover manifest loading, capability binding, dependency order, reverse shutdown, operation validation, implementation restrictions, test execution, and hardware-test approval.
