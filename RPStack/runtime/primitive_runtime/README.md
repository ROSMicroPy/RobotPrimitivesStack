# PrimitiveRuntime

MicroPython-compatible runtime support for Robot Primitive manifests.

The package provides:

- manifest loading and structural validation;
- capability matching with interface versions and semantic constraints;
- explicit or automatic dependency binding;
- dependency-ordered construction and startup;
- reverse-order shutdown and startup rollback;
- allowlisted operation invocation;
- declarative manifest test execution.

```python
runtime = ServiceSupervisor()
runtime.register("motor", motor_manifest, factory=make_motor,
                 implementation="step_dir")
runtime.register("position", position_manifest, factory=make_position)
runtime.register(
    "slide",
    slide_manifest,
    factory=LinearSlide,
    bindings={"motor": "motor", "position": "position"},
)
runtime.start()
runtime.invoke("slide", "move_to", {"target": 0.1})
```

YAML parsing is intended for host tooling. Deploy generated JSON manifests on
stock MicroPython targets to avoid carrying a YAML parser in firmware.
