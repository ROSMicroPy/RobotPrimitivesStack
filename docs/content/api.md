# API Reference

## Native REPL helpers

These functions are installed by the slide demo package, not by every RPStack node.

| Function | Behavior |
| --- | --- |
| `start()` | Start the local slide provider and return to the prompt |
| `start('client')` | Start a client host without local hardware |
| `position(timeout_s=5)` | Request a canonical position sample without motion |
| `calibrate(steps=1000, timeout_s=30)` | Explicit forward/reverse distance test |
| `set_range(min_mm, max_mm, timeout_s=5)` | Update provider target bounds until restart |
| `demo(position_mm=100, timeout_s=30)` | Run one correlated absolute move request |
| `status()` | Return the local host snapshot |
| `stop()` | Shut down the local host and its owned work |

Remote commands use the same helpers. A timeout describes the missing outcome, not proof of remote cancellation.

## Service operations

From inside an async app:

```python
await node.invoke('slide', 'set_range', {'min_mm': 30, 'max_mm': 300})
bounds = await node.invoke('slide', 'get_range', {})
position = await node.invoke('slide', 'move_to', {'target': 0.1})
```

`move_to` uses metres. `set_range` uses explicitly named millimetre arguments. Other slide operations include `observe_position`, `status`, `calibrate`, `jog_steps`.

## HTTP task API

HTTP is available only when the node manifest enables `rpstack.micropyserver:NodeRestApi` and suitable networking. The slide-node demo includes HTTP, catalog and gateway runtimes on the provider and persistent client host. Configure Wi-Fi before starting; use the printed gateway URL.

| Method and path | Purpose |
| --- | --- |
| `GET /manifest` | Public service/operation discovery |
| `POST /api/services/{service}/{operation}` | Submit declared service operation |
| `GET /api/tasks` | Task list and retained outcomes |
| `GET /api/task?id=ID` | Inspect a task result or error |
| `POST /api/task/cancel` | Cancel operation/flow: `{"id": ID}` |
| `GET /api/node/status` | Node state, including calibration |
| `POST /api/node/calibrate` | Calibrate all services or one selected service |
| `POST /api/node/stop` | Stop managed application work |
| `POST /api/node/reset` | Rebuild application services |

```sh
curl -X POST http://DEVICE/api/services/slide/set_range   -H 'Content-Type: application/json'   -d '{"min_mm":30,"max_mm":300}'
```

Ordinary operations return HTTP 202 with `task_id` and `status_url`. Follow that URL for completion; acceptance alone is not success. Runtime discovery generates these service paths from service IDs and operation names.

## Slide signal protocol

| Request | Arguments | Successful terminal reply |
| --- | --- | --- |
| `slide.ping` | Empty | `slide.ready` |
| `slide.observe` | Empty | `slide.position` |
| `slide.calibrate` | `steps` | `slide.calibrated` |
| `slide.set_range` | `min_mm`, `max_mm` | `slide.range.updated` |
| `slide.move` | `position_mm` | `motion.target.reached` |

Commands require an explicit target and nonempty correlation ID. Failures use `motion.target.failed`, including observation and configuration errors. Only motion/calibration requests emit `motion.started`. The ready reply identifies the command protocol version.
