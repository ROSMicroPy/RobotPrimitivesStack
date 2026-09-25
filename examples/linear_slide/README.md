# Manifest-driven linear slide node

`manifest.json` is the complete application definition. `main.py` only calls
`run_manifest("/lib/linear_slide_manifest.json")`. No application assembly or pin
configuration is required in Python.

The `rp.node/v1` manifest contains:

- `resources`: shared platform resources (the carriage I2C bus).
- `components`: embedded `rp.service/v1` contracts, including driver entry points.
- `services`: named instances, selected implementations, constructor arguments,
  configuration, and explicit capability bindings.
- `runtime`: ordered runtime services: WiFi, HTTP, and the asyncio console.
- `flows`: optional signal-driven execution graphs. Initialization automatically calibrates with 1,000 steps in each direction.

The runtime validates configuration and dependencies, creates resources and
services in dependency order, and registers all resident tasks. Passive adapters
have a resident waiting task, so they also appear in `ps`. Services receive their
dependencies from the runtime and never construct hidden child services.

## Install and boot

From this directory:

```sh
mpremote mip install package.json
mpremote fs cp main.py :main.py
```

The package installs libraries and the manifest under `/lib`. The second command
installs the generic entry point as the device's boot `/main.py` (replacing an
existing boot entry). `package.github.json` is the equivalent dependency list
for a published repository; local installation does not need public GitHub.

Local package dependencies are listed here at the application level because
`mpremote` resolves dependency paths from the working directory. After an
interrupted install, rerun the install command to complete it.

Configure credentials once through the MicroPython REPL before booting:

```python
from rpstack.env import setEnv
setEnv("WIFI_SSID", "your-network", True)
setEnv("WIFI_PASSWORD", "your-password", True)
```

Then reset the device. The node uses I2C bus 0 (SDA 5, SCL 4), STEP 17, DIR 3,
and ENABLE 21; all are editable in the manifest. The sensor address is 41 and
its timing budget is 50 ms. `positive_direction`, travel limits, step timing,
and sampling batch size are manifest configuration values.

## Console

```text
ps
status
run slide jog_steps {"steps":200,"direction":true}
stop
reset
kill 12
flow observe_on_signal
signal observe {"source":"console"}
```

`ps` lists real tracked asyncio tasks, not OS threads. `run` returns a task ID.
`stop` cancels operations and flows, disables motion, and stops application
services in reverse dependency order. HTTP and the console remain available.
`reset` cancels old work, releases services, and constructs fresh instances from
the same manifest; it does not reboot the board or resume old workflows. Ctrl-C
in the console requests a full application stop. `kill` cancels an operation or
flow; use `stop` for services.

## Web Tester / REST

Connect the Web Tester to `http://<device-ip>/manifest`. Discovery lists every
service and separate node controls. It omits deployment resources and runtime
configuration. An operation request looks like:

```text
POST /api/services/slide/move_to
{"target":0.1}
```

Long and short ordinary operations return HTTP 202 with `task_id` and
`status_url`. Poll that URL for `pending`, `running`, `succeeded`, `failed`, or
`cancelled`, and the final `result`/`error`. The Web Tester polls automatically;
202 means accepted, not completed. Completed task history is bounded; expired
IDs return 404.

```text
GET  /api/node/status
GET  /api/tasks
POST /api/node/stop
POST /api/node/reset
POST /api/task/cancel   {"id":12}
POST /api/flows/start   {"name":"observe_on_signal"}
POST /api/signals        {"name":"observe","payload":{}}
```

Exclusive operations reserve their service and transitive dependencies before
scheduling. Conflicting work returns 409. Cached service status and node controls
bypass that queue. Invalid arguments return 422. Multiple clients and incomplete
HTTP requests cannot monopolize the listener.

## Validation and timing

Host tests cover manifest-only assembly, simultaneous HTTP clients, movement
cancellation, stop/reset, signal waits, failed initialization, and argument
validation using simulated pins/sensors. Hardware deployment is not exercised
by those tests. Async pulse delays are minimum delays and depend on event-loop
scheduling; this implementation is not a precise high-rate pulse generator.
Native I2C transactions remain synchronous bounded calls. Confirm pulse timing
and stop latency on the target board; use a hardware pulse peripheral for tighter
timing requirements.

The deployment also runs `rpstack.catalog:Catalog` and the `robot_gateway` app
on its existing HTTP listener. Query `/api/robot` or use RobotArchitect System.
The default local signal route lists only this node; configure a mesh transport
and route to discover the complete robot.
