# Linear Slide Application

`LinearSlide` combines the universal MotorControl stepper driver with the
DistanceSensor VL53L4CD driver. The sensor is configured with a 200 ms timing
budget. Motion is closed-loop: the class reads the position, moves one step in
the required direction, and reads again until it reaches the requested position.

```python
from LinearSlide import LinearSlide

slide = LinearSlide(
    i2c,
    step_pin=17,
    dir_pin=3,
    enable_pin=21,
    positive_direction=True,
    tolerance_mm=1,
    min_position_mm=20,
    max_position_mm=300,
)

print(slide.getPosition())
slide.gotoPosition(100)
slide.shutdown()
```

Set `positive_direction=False` if a `False` MotorControl direction increases the
ToF reading on the assembled slide. Configure physical minimum and maximum
positions whenever possible. `max_steps` is an additional safety guard for a
blocked mechanism or failed sensor.
