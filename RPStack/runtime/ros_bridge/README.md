# ROS signal transport

`rpstack.ros_bridge:RosTransport` publishes/subscribes `std_msgs/msg/String` on
`/rpstack/<entity>/signals` (override with `topic`). Each message contains the
same compact JSON envelope used locally and over mesh. ROS participants should
use the signal codec and stable node/boot identities. This does not automatically
map arbitrary typed ROS topics into primitive operations.

Use `backend: "rclpy"` for CPython ROS 2. The async receive task calls
`spin_once(node, timeout_sec=0)` and yields between polls. The adapter destroys
its node and shuts down a context only when it initialized it. Keep entity and
node identifiers valid for ROS topic/node names (letters, digits, underscores;
node names must not start with a digit). Node-name hyphens are converted to
underscores and prefixed with `rpstack_`.

Use `backend: "rosmicropy"` for the included firmware. Its `spin_once()` is a
stub, so this adapter explicitly starts the native `run_ROS_Stack()` worker.
RPStack creates no Python worker thread. Native callbacks copy strings into a
bounded mailbox guarded by a lock; only the asyncio loop decodes/routes them.
The included Python shim is exercised directly by a host test with the native
module substituted.

The reference firmware cannot unregister subscriptions or stop its native ROS
worker. On stop, callbacks become inert; a second native adapter is rejected
until reboot. Do not call `rclpy.shutdown()` externally to try to reset this
firmware worker: it only resets Python flags. RPStack application stop/reset
keeps the transport running, so ordinary service reset does not need a reboot.
Only one ROSMicroPy adapter may own the native stack on a device.

Other configuration: `qos` (10), `poll_ms` (10), `queue_limit` (32), `max_bytes`
(2048), and `init` keyword arguments forwarded to `rclpy.init` (e.g. the
ROSMicroPy agent address/port). Queue overflow drops new messages and increments
`transport.dropped`. Mesh/ROS echo loops are suppressed by the shared bus.
Actual ROS 2 middleware and micro-ROS agent communication still need hardware
and environment validation.
