# Typed ROS slide gateway

`SlideRosBehavior` is an optional **desktop CPython/rclpy** resident behavior that exposes
an SomaticMesh slide as native ROS interfaces. Controllers continue to use
**ROSMicroPy's frozen rclpy implementation and micro-ROS**. That implementation
supports typed publishers/subscribers but currently has no action server,
executor, or working future API; the desktop behavior supplies the action facade.

The gateway does not replace the device supervisor, bypass resource claims, or
require The Loom to remain open. It uses the existing leased remote
execution protocol over any configured SomaticMesh signal transport.

## Interfaces

With namespace `somatic_mesh/slide`:

| Endpoint | ROS interface | Behavior |
| --- | --- | --- |
| `/somatic_mesh/slide/position` | `somatic_mesh_interfaces/msg/LinearPosition` | Measured linear position, validity, quality, frame, and original device timestamp |
| `/somatic_mesh/slide/move` | `somatic_mesh_interfaces/action/MoveLinear` | Absolute target in metres, measurement feedback, confirmed or unconfirmed terminal result |
| `/somatic_mesh/slide/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | Readiness, motion, stale connectivity, and latched uncertain outcomes |

Build the generated interface package under `ros2/somatic_mesh_interfaces` using colcon
before loading the behavior. Importing the SomaticMesh package itself does not import ROS.
The behavior owns a separate rclpy context and cooperatively polls its executor; it
does not shut down a context belonging to the signal transport or another behavior.

See `examples/ros_slide/README.md` for the complete firmware-to-agent-to-gateway
deployment and commands.

## Runtime semantics

- Both nodes declare each other in `execution.peers`; the worker exposes the slide
  in `execution.expose`. Device operation allowlists and resource claims remain
  authoritative, including when a local workflow competes with a ROS goal.
- One goal is admitted at a time, after fresh health and valid position checks,
  active/calibrated status, and range checks. The worker still validates again at
  dispatch. No automatic calibration or hardware reassignment occurs.
- Position feedback comes from the service's actual measurements with
  `inject_signals: true` and a `signal_id` matching its service ID. Feedback may be
  sparse during a long blocking motor batch. No competing sensor reads are made
  during motion.
- ROS cancel requests set a cancellation event. The remote protocol stops renewing
  the operation lease and requests cancellation. A canceled ROS result requires
  worker confirmation after managed cleanup, or confirmation that dispatch never
  occurred. Successful completion racing cancellation remains successful.
- Timeout, disconnect, or generation change never triggers a movement retry.
  An uncertain outcome aborts and latches admission closed. Inspect the device and
  restart the gateway to re-establish readiness; a desktop timeout does not prove
  physical motion stopped. Cooperative leases are not hardware emergency stops.
- Header timestamps on gateway position messages use **gateway receipt time**.
  `source_timestamp_ns` preserves the device timestamp on its own clock, with a
  separate validity bit. No clock synchronization or coordinate transform is
  implied. `frame_id` configuration is only a label override for the same frame.
- Position uses sensor-data QoS. Diagnostics are volatile and refreshed every
  0.5 seconds; consumers must still detect gateway disappearance. Underlying ROS
  delivery policies do not strengthen an ESP-NOW segment's delivery guarantees.

## Configuration

Actor assignment fragment:

```json
{
  "id": "ros",
  "behavior": "somatic_mesh.behaviors.ros_gateway:SlideRosBehavior",
  "config": {
    "target_node": "slide_device",
    "service": "slide",
    "namespace": "somatic_mesh/slide",
    "health_timeout_s": 1.0,
    "inventory_interval_s": 5.0,
    "move_timeout_s": 60.0,
    "cancel_timeout_s": 3.0
  }
}
```

Health probes do not consume remote operation history. Idle status and position
refreshes do; the minimum refresh interval is 3 seconds and the default is 5.
Budget the worker's execution capacity for other clients too. This first adapter
is intentionally a linear-slide profile, not a generic descriptor-to-ROS compiler.
The software registry/provisioning design remains separate proposed work.

## Verification

```sh
python3 -B -m unittest discover -s SomaticMesh/behaviors/ros_gateway/test -v
```

Host integration tests run real SomaticMesh nodes over a simulated lossy transport.
Real rclpy tests additionally require desktop ROS and the built interface package;
they explicitly skip otherwise. `.github/workflows/ros-gateway.yml` builds the
interfaces and runs both sets on ROS 2 Jazzy. Firmware shim tests live under
`SomaticMesh/transports/ros_signals/test`; native radio/agent timing requires hardware.
