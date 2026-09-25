# Linear slide nodes: install and run from the REPL

Install **the same package on each ESP32 device**. The installed manifests use
`SharedEspNowTransport`: each signal is delivered to local nodes and broadcast
via ESP-NOW. Moving node2 to another device requires no changes to the manifests
or application code. Both radios use channel 6 by default and entity `SlideDemo`.

Node1 owns the motor, VL53L4CD TOF sensor, position adapter, and LinearSlide.
Node2 is a one-off client: request a move, print replies, then exit. Node1 remains
resident. Each node has its own services, tasks, and signal bus.

## Install all code

From the repository root, connect one board and run:

```sh
cd examples/slide_nodes
mpremote mip install package.json
mpremote repl
```

If several boards are connected, select each board explicitly:

```sh
mpremote connect /dev/ttyACM0 mip install package.json
mpremote connect /dev/ttyACM0 repl
```

Repeat the install on the second board if using two devices. `package.json`
installs the slide, gateway, catalog, HTTP, environment and runtime dependencies plus these files:

- `/lib/slide_nodes.py`: native-REPL launch helpers.
- `/lib/slide_node1.json`: slide service manifest, from `node1.device.json`.
- `/lib/slide_node2.json`: one-off client manifest, from `node2.device.json`.
- `/lib/slide_client_host.json`: persistent client gateway, from `client_host.device.json`.

Installation does not replace `/main.py` or start motion. The launcher needs exclusive ownership
of the asyncio loop and ESP-NOW radio. The board must provide `_thread`,
`asyncio`, `network`, `espnow`, and the usual `machine` hardware APIs.

Configure node1's hardware and calibration before running. Defaults are I2C bus
0, SDA 5, SCL 4, STEP 17, DIR 3, ENABLE 21, sensor address 41. Edit
`node1.device.json` and reinstall, or edit `/lib/slide_node1.json` on the board.
Set installation coordinates and minimum/maximum travel for your slide.
Calibration determines the electrical direction.
The default demo target is an absolute **100 mm** position.

## Wi-Fi and RobotArchitect catalog

Version 0.3.0 includes the gateway app. Configure Wi-Fi on each physical device
before `start()` (or connect its station interface beforehand):

```python
from rpstack.env import setEnv
setEnv("WIFI_SSID", "your-network", True)
setEnv("WIFI_PASSWORD", "your-password", True)
```

These credentials are persisted on the device, not included in catalog profiles.
The access point channel must match the ESP-NOW channel in **both**
`slide_node1.json` and `slide_node2.json`, plus `slide_client_host.json`.
The shipped channel is 6. HTTP gateways require a reachable Wi-Fi network;
an ESP-NOW-only setup cannot be reached by RobotArchitect's HTTP client.

`start()` hosts the gateway on node1, alongside the slide command app.
`start("client")` hosts a resident `node2-host` with its own gateway and catalog;
it owns no slide hardware. The temporary `node2` move app remains one-off and
shares the resident host's radio. Ending a command does not close the gateway.
Keep node1, node2-host and the active node2 unique within `SlideDemo`.

Startup prints `RobotArchitect gateway: http://<address>:80`. Retrieve it with
`slide_nodes.status()["gateway_url"]`. Open RobotArchitect's **System** view and
enter that base URL. It can attach to either device to fetch `/api/robot` and
see the local node plus discovered peers, service capabilities and apps.
The same server retains `/manifest`, task and service-operation APIs.
This development API includes motion controls: use a trusted network.

Discovery is eventually consistent: profiles normally announce every 5 seconds
and expire after 20 seconds. Allow several seconds after peer startup.
A brief one-off node2 may finish before its complete profile reaches every peer;
node1 and node2-host remain discoverable while running. Catalog traffic waits
for empty outbound queues so profile fragments do not fill the command queue.
Stopping the client host stops its gateway but does not stop remote slide motion.

For an ESP-NOW-only deployment, remove `wifi` and `http` runtime entries and the
`gateway` app from the resident manifests; keep `catalog` if mesh discovery is
still wanted. This intentionally disables RobotArchitect's HTTP attachment.

## One device: start, return to the prompt, run the demo

At the native MicroPython prompt:

```python
import slide_nodes
slide_nodes.start()
# Returns {'state': 'running', ...}; node1 keeps running at the >>> prompt.

slide_nodes.calibrate(steps=1000)  # Explicit forward/reverse distance test.
slide_nodes.demo()       # Run node2 once, move to 100 mm, print signals, return.
slide_nodes.demo(120)    # Another one-off node2, absolute 120 mm.
slide_nodes.status()
slide_nodes.stop()       # Cancel work, stop the motor, release both nodes/radio.
```

Typical demo output:

```text
motion.started {'position_mm': 100}
motion.target.reached {'value': 0.1, 'unit': 'm', ...}
```

`demo()` also returns the final PositionSample dictionary. It waits until success,
error, or timeout; afterward the native prompt returns and node1 is still running.
Calling `demo()` again creates a fresh client node and correlation ID. After
`stop()`, `start()` can initialize a fresh slide node.

## Two devices: exactly the same installed code and manifests

On **device A**, wired to the motor and TOF sensor:

```python
import slide_nodes
slide_nodes.start()      # Start node1 and return to the native prompt.
slide_nodes.status()
```

On **device B**, which requires no motor or sensor:

```python
import slide_nodes
slide_nodes.start("client")  # Start the persistent gateway without slide hardware.
slide_nodes.calibrate(steps=1000)  # Calibrate node1 remotely, with clearance.
slide_nodes.demo()           # Send to node1 on device A; print replies on B.
slide_nodes.demo(120)
slide_nodes.stop()           # Stop this device's client host only.
```

On device A, `slide_nodes.stop()` stops the slide. Stopping device B does not stop
an ongoing move on A. `status()['node1'] == 'remote'` on B describes placement,
not a continuously monitored remote health state. The demo probes readiness.

Both devices must use the same ESP-NOW channel, and be within radio range. ESP-NOW itself does not require a router, but the HTTP gateways use Wi-Fi. If already connected to Wi-Fi, its channel
must match the configured radio channel. Keep one node1 and at most one active
node2 per entity, including local and remote clients. Use another entity for a
second independent slide installation. Replies retain their requester target and
correlation ID, so unrelated nodes do not consume them as their own results.

## REPL and transport behavior

Startup imports runtime/app/driver modules and reads both manifests on the
foreground stack before creating any worker. A single background `_thread`
then owns the asyncio loop and all node objects, with an explicit 64 KiB stack.
Each motion batch uses a separate 64 KiB pulse worker; TOF reads wait until that
worker has finished.
The previous thread-stack default is restored after launching it.
`start(verbose=False)` suppresses startup messages; `start(stack_size=65536)`
sets the stack explicitly (minimum 32768 bytes). The
native REPL sends bounded requests through a lock; it never schedules tasks from
another thread. Do not run a second asyncio loop or independently activate
ESP-NOW while this launcher is active. MicroPython documents `_thread` as
[experimental](https://docs.micropython.org/en/latest/library/_thread.html), so
board/firmware verification is still required. Ctrl-C during `demo()` cancels the
local client wait; call `stop()` on the slide device to stop motion. Ctrl-D resets
the device and discards the running nodes.

`SharedEspNowTransport` owns one radio per interpreter and serializes fragmented
transmissions. Local nodes share that radio and have separate bounded receive
queues. Stopping node2 leaves node1's radio active. The last node closes the radio.
Radio receive failures propagate to node health. Ordinary `EspNowTransport`
instances must not separately own the same radio.

The client retries harmless readiness probes until node1 is ready, then sends
**one move command**. The total timeout (readiness plus motion) defaults to 30
seconds: `slide_nodes.demo(100, timeout_s=60)` changes it. Radio delivery remains
best effort; motor commands are not automatically retried. A lost command or
terminal event results in timeout. A timeout does not imply that motion stopped.
This is a tested demo/protocol implementation, not a guaranteed-delivery motion
controller.

## Command contract and lifecycle

Publish `slide.move` with `{"position_mm": 100}`, target `node1`, and a unique
nonempty correlation ID. The service accepts explicitly targeted commands only.
It submits moves through the supervisor, which validates arguments and reserves
the slide and dependent devices. Concurrent moves are rejected as busy.

Replies target the requester and retain the correlation ID:

- `motion.started`: managed move submitted and beginning execution; this is not
  sensor confirmation of physical displacement.
- `motion.target.reached`: final canonical PositionSample in metres.
- `motion.target.failed`: invalid command, busy resources, sensor/motion failure,
  or cancellation error.

`slide.ping` / `slide.ready` implement readiness without moving hardware. The
client subscribes before publishing and filters source and correlation.

Apps default to `mode: resident`; `mode: oneshot` permits successful return.
When all apps are oneshot, `NodeRuntime.wait()` waits for their results and
propagates failures. The manifest runners shut down completed task-only nodes;
mixed nodes remain resident. `NodeHost.failures` records failed task-only nodes
without stopping resident peers.

For boot-time execution without a native REPL, the same installed manifests work
with `run_manifest('/lib/slide_node1.json')` or
`run_manifests(['/lib/slide_node1.json', '/lib/slide_node2.json'])`. Do not use these
alongside the background launcher. Startup remains stationary; an explicit
calibration request is required before the one-off move client can succeed.

Logical isolation is not OS security or hardware arbitration. Only one node
should own a given motor, sensor, peripheral, or listening port.

## Host simulation and validation

From the repository root:

```sh
python3 examples/slide_nodes/demo.py
```

The host simulation uses `node1.json` / `node2.json` (in-process transport) with
simulated motor/TOF drivers and the real LinearSlide/service supervisor. The
device installer instead uses the `.device.json` pair for both physical layouts.

Automated tests cover one shared radio and two simulated radios, command/event
routing, readiness, duplicate identities, channel conflicts, native-REPL
start/demo/stop/restart, package completeness, busy rejection, stalled motion,
and failure isolation. Physical ESP32 radio, thread stability, and motor timing
have not been verified here.

## Motion timing and calibration

The slide manifests select `step_delay_us: 100`. This is
100 µs HIGH plus 100 µs LOW: nominally 5,000 pulses/second before Python/GPIO/thread
overhead. It is not a guaranteed pulse frequency or acceleration profile.

```python
import slide_nodes
slide_nodes.start()             # No movement on init/start.
report = slide_nodes.calibrate(steps=1000)
print(report)                   # positions_mm, forward_mm, reverse_mm,
                                # steps_per_mm, positive_direction
slide_nodes.demo(100)
slide_nodes.status()            # Includes local slide calibration/pulse_mode.
```

The calibration sends uninterrupted pulses for each leg and measures only before,
between, and after the legs. Choose fewer steps if 1,000 would exceed available
travel; too little measured displacement is rejected as unreliable. Target moves
use a continuous run covering approximately 96% of the measured error, then fresh
TOF measurements and smaller corrections. Brief pauses at those batch boundaries
are expected; TOF reads are not interleaved with individual pulses. A clearly
wrong-direction batch stops immediately instead of waiting for three batches.

The VL53L4CD can hold a completed range until its interrupt is acknowledged. The
driver discards any held/in-flight result and waits for a new exposure when a
stationary position is requested. This prevents the previous movement's stale
sample from deciding scale or direction. See the
[ST ranging handshake description](https://www.st.com/resource/en/datasheet/vl53l4cd.pdf).

A timed-out client is not proof that the motor stopped. On the slide device,
`slide_nodes.stop()` cancels its managed operation and waits for pulse-worker
cleanup. Calibration runs and target moves both remain bounded by step limits.

## Check TOF readings without moving

After `start()`, call `slide_nodes.position()` locally, or after
`start("client")` on the other device. This reads node1's position through the
same signal transport without commanding motor pulses or requiring calibration.
The returned dictionary uses metres: `value=0.1` means 100 mm.

```python
print(slide_nodes.position())
# Present a target at a different distance in front of the TOF, then repeat.
print(slide_nodes.position())
```

If calibration reports too little displacement despite visible carriage motion,
check these readings before another calibration. Confirm the sensor sees the
moving target rather than a fixed surface. Calibration errors include the
direction, pulse count, before/after distances, measured delta, and required
minimum delta in mm. A failed calibration leaves target moves disabled and does
not automatically retry movement. 

During calibration, the slide device prints the start and end TOF-derived
position in mm for each forward/reverse run, including the measured change.
These use the configured position adapter's offset and direction. The end
reading prints before the displacement check, so it is visible even when that
check fails. No additional sensor reads are made during movement.

## Travel range

The node1 manifests set `services.slide.config.min_position_m` to `0.03` and
`max_position_m` to `0.3`: absolute target positions of 30–300 mm, inclusive,
in the position adapter's coordinate system. Targets outside this range fail
before motor pulses. Status includes `range_mm` and `max_steps`.

```python
slide_nodes.set_range(30, 300)  # Local or remote; returns the accepted bounds.
slide_nodes.demo(200)
```

API range changes take effect without movement and last until restart. Edit the
manifest and reinstall to change startup defaults. Both bounds must be finite,
with minimum less than maximum; updates are rejected during active motion.
When the REST server is enabled, `POST /api/services/slide/set_range` accepts
`{"min_mm": 30, "max_mm": 300}`, and `POST /api/services/slide/get_range` with `{}` reads the bounds.
These return a task ID; retrieve the result using `/api/task?id=<task_id>`.
The service operations are `set_range` and `get_range`.

These are target limits, not physical limit switches: calibration and fixed-step
jogs still require clearance and are not constrained by these target bounds.
The demo's separate `max_steps` cap is 100000. At about 222 steps/mm, a
100 mm move needs roughly 22200 steps; the former 10000 cap was insufficient.
The step cap remains fixed when changing the range and prevents unlimited motion.
