# Linear Slide Composite

`LinearSlide` is a composite `motion.position_actuator`. Its primary constructor
accepts two runtime-bound roles:

- `motor`: a `motion.motion_actuator` in incremental mode
- `position_observer`: a linear `motion.position_observer` using metres

```python
slide = LinearSlide(motor=stepper, position_observer=carriage_position)
final_sample = slide.move_to(0.100)
```

The composite owns mechanism behavior—target tolerance, direction, travel
limits, cancellation, and maximum increments—but does not own dependencies
injected by the runtime. `shutdown()` stops them without shutting them down.

The original I2C/pin constructor and millimetre methods remain available for
existing deployments. That compatibility path assembles the `step_dir`,
`vl53l4cd`, and distance-to-position services internally and owns their
lifecycle.
