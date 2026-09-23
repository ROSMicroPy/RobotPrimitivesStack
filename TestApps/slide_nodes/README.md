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
cd TestApps/slide_nodes
mpremote mip install package.json
mpremote repl
```

If several boards are connected, select each board explicitly:

```sh
mpremote connect /dev/ttyACM0 mip install package.json
mpremote connect /dev/ttyACM0 repl
```

Repeat the install on the second board if using two devices. `package.json`
installs all nine local RPStack package dependencies plus these files:

- `/lib/slide_nodes.py`: native-REPL launch helpers.
- `/lib/slide_node1.json`: slide service manifest, from `node1.device.json`.
- `/lib/slide_node2.json`: one-off client manifest, from `node2.device.json`.

Installation does not replace `/main.py` or start motion. If an older application
starts at boot, stop it before using this launcher. It needs exclusive ownership
of the asyncio loop and ESP-NOW radio. The board must provide `_thread`,
`asyncio`, `network`, `espnow`, and the usual `machine` hardware APIs.

Configure node1's hardware and calibration before running. Defaults are I2C bus
0, SDA 5, SCL 4, STEP 17, DIR 3, ENABLE 21, sensor address 41. Edit
`node1.device.json` and reinstall, or edit `/lib/slide_node1.json` on the board.
Set direction, position calibration, and minimum/maximum travel for your slide.
The default demo target is an absolute **100 mm** position.

## One device: start, return to the prompt, run the demo

At the native MicroPython prompt:

```python
import slide_nodes
slide_nodes.start()
# Returns {'state': 'running', ...}; node1 keeps running at the >>> prompt.

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
slide_nodes.start("client")  # Start the background loop without local hardware.
slide_nodes.demo()           # Send to node1 on device A; print replies on B.
slide_nodes.demo(120)
slide_nodes.stop()           # Stop this device's client host only.
```

On device A, `slide_nodes.stop()` stops the slide. Stopping device B does not stop
an ongoing move on A. `status()['node1'] == 'remote'` on B describes placement,
not a continuously monitored remote health state. The demo probes readiness.

Both devices must use the same ESP-NOW channel, and be within radio range. No
Wi-Fi credentials/router are required. If already connected to Wi-Fi, its channel
must match the configured radio channel. Keep one node1 and at most one active
node2 per entity, including local and remote clients. Use another entity for a
second independent slide installation. Replies retain their requester target and
correlation ID, so unrelated nodes do not consume them as their own results.

## REPL and transport behavior

Startup imports runtime/app/driver modules and reads both manifests on the
foreground stack before creating any worker. A single background `_thread`
then owns the asyncio loop and all node objects, with an explicit 64 KiB stack.
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
alongside the background launcher.

Logical isolation is not OS security or hardware arbitration. Only one node
should own a given motor, sensor, peripheral, or listening port.

## Host simulation and validation

From the repository root:

```sh
python3 TestApps/slide_nodes/demo.py
```

The host simulation uses `node1.json` / `node2.json` (in-process transport) with
simulated motor/TOF drivers and the real LinearSlide/service supervisor. The
device installer instead uses the `.device.json` pair for both physical layouts.

Automated tests cover one shared radio and two simulated radios, command/event
routing, readiness, duplicate identities, channel conflicts, native-REPL
start/demo/stop/restart, package completeness, busy rejection, stalled motion,
and failure isolation. Physical ESP32 radio, thread stability, and motor timing
have not been verified here.

## Startup crash on ESP32-S3 (MicroPython v1.28.0)

The reported `LoadProhibited` dump matched the official Octal-SPIRAM ELF hash
`7efd4e2f92ee30446a8ad3d572f4d792e869478ac58eca093847695269b78aef`.
Decoded frames show nested worker-thread imports, LittleFS reads, and a fault in
`tlsf_walk_pool` during native heap inspection. This identifies the failure path;
it does not establish the original source of memory corruption. The old launcher
used the firmware's small default worker stack and imported everything there.
Version 0.1.1 preloads modules/manifests on the foreground stack, requests a 64 KiB
worker stack, and prints startup stages. Python startup errors are raised at the
REPL before a worker is launched when possible.

To update just the launcher from the repository root, preserving device-specific
manifest/pin settings:

```sh
mpremote fs cp TestApps/slide_nodes/device.py :/lib/slide_nodes.py
mpremote repl
```

Press Ctrl-D to restart the interpreter, then:

```python
import slide_nodes
slide_nodes.start()
```

For the remote client, use `slide_nodes.start("client")` as before. If another
native crash occurs, retain the last `[slide_nodes]` startup message and full
dump. The larger stack and startup restructuring are verified by host tests and
a Unix MicroPython 1.26.1 installed-package simulation; this ESP32 firmware fix
still needs verification on the physical board. The matching ELF decoding method
is described in the [MicroPython debugging guide](https://github.com/micropython/micropython/wiki/ESP32-debugging).
