# Linear slide with ROSMicroPy and ROS 2

The controller runs RPStack on ROSMicroPy and communicates with a micro-ROS agent.
It publishes a typed prismatic-joint measurement directly through the firmware's
`rclpy` API. An optional desktop gateway adds a standard ROS action, richer typed
position feedback, and diagnostics. No Robot Architect process is required.

## Controller

Start from a ROSMicroPy firmware image. Review `device.json` for the actual board's
pins, I2C configuration, travel range, and agent IP/port before installation. It
uses the same hardware assumptions as the existing slide-node example.

From this repository root, with the target attached over USB:

```sh
mpremote mip install examples/ros_slide/package.json
```

Set `WIFI_SSID` and `WIFI_PASSWORD` using the existing environment configuration,
then start the node on the device:

```python
from rpstack.node_runtime import run_manifest
run_manifest('/lib/ros_slide.json')
```

The included HTTP control remains available on port 80. Calibrate explicitly using
the existing node calibration endpoint after checking travel and clearance:

```sh
curl -X POST http://DEVICE_IP/api/node/calibrate \
  -H 'Content-Type: application/json' \
  -d '{"service":"slide","arguments":{"steps":1000}}'
```

Wait for calibration completion before sending a move. The gateway rejects goals
until it observes an active calibrated slide and a valid measured position. This
is local slide readiness, not the proposed robot-wide startup barrier.

## Agent and desktop gateway

Run a micro-ROS agent matching the firmware, for example its `udp4 --port 8888`
mode. Ensure the configured agent address is reachable from the controller and
the agent and desktop ROS processes use the intended ROS domain.

On a ROS 2 Jazzy host with `colcon`, `rclpy`, `sensor_msgs`, and `diagnostic_msgs`,
build the interface definitions and run the gateway from the repository root:

```sh
source /opt/ros/jazzy/setup.bash
colcon --log-base /tmp/rpstack-ros-log build --base-paths ros2 \
  --build-base /tmp/rpstack-ros-build --install-base /tmp/rpstack-ros-install
source /tmp/rpstack-ros-install/setup.bash
python3 examples/ros_slide/run_gateway.py
```

Source the same ROS and interface setup files in another terminal:

```sh
ros2 topic echo /rpstack/slide_device/joint_states
ros2 topic echo /rpstack/slide/position
ros2 topic echo /rpstack/slide/diagnostics
ros2 action send_goal /rpstack/slide/move rpstack_interfaces/action/MoveLinear \
  '{target_m: 0.1}' --feedback
```

`target_m` is an absolute target in metres. Closing an action client terminal is
not a confirmed cancellation; use a ROS action client that issues `cancel_goal_async`
and observes the terminal result. A lost reply is reported as unconfirmed and
must not be treated as evidence that no movement occurred.

## Direct firmware telemetry

The transport's optional `publishers` profile maps measured slide signals to
`sensor_msgs/msg/JointState`. Publishers are registered before starting the native
ROS worker, and the existing String envelope transport remains available for
RPStack execution. Only the configured service on the local node is projected;
relayed peers and invalid samples are excluded.

The firmware currently lacks a synchronized ROS clock API, so its direct joint
state header stamp is zero (unspecified). A device monotonic timestamp is never
presented as ROS time. The gateway's `LinearPosition` instead carries receipt time
and the original device timestamp separately. Neither path performs transforms.

The ROSMicroPy shim currently accepts QoS arguments but does not apply them to its
native publisher/subscriber creation. Direct firmware publisher QoS therefore
follows the native implementation. Full ROS actions, futures, and executors belong
to the desktop adapter until equivalent firmware APIs exist.

Only one ROSMicroPy transport may own the native worker on a device. Stopping and
recreating that worker still requires reboot; application service reset keeps it
running. Health diagnostics and action arbitration do not add authentication to the
RPStack signal protocol.
