# RPStack MicroPyServer

`rpstack.micropyserver` provides a small synchronous HTTP server and the
standard REST adapter for `rp.service/v1` services.

```python
from rpstack.micropyserver import MicroPyServer, ManifestRestApi

server = MicroPyServer(port=80)
ManifestRestApi(server, manifest, distance_sensor)
server.start()
```

The adapter always exposes `GET /manifest`. Each operation uses its optional
`rest.method` and `rest.path`; otherwise it uses
`POST /api/operations/<operation-name>`. Only declared operations can be
called. JSON responses, CORS headers, and OPTIONS preflight are included.

The VL53L4CD device configuration uses serializable pin identifiers:

```json
{"implementation": "vl53l4cd", "i2c": {"scl": 4, "sda": 5, "address": 41}}
```

The application layer converts these to
`I2C(..., scl=Pin(4), sda=Pin(5))`; executable Python expressions are never
sent over REST.
