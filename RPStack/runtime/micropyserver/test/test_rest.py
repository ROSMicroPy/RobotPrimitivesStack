import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rpstack.micropyserver import ManifestRestApi


MANIFEST = {
    "manifest": "rp.service/v1",
    "service": {
        "name": "test-distance", "version": "1",
        "kind": "individual_driver", "type": "sensor.distance",
        "operations": {
            "read": {
                "method": "read",
                "arguments": {"samples": {"type": "integer", "required": True}},
                "rest": {"method": "POST", "path": "/api/distance/read"},
            }
        },
    },
}


class FakeServer:
    def __init__(self):
        self.routes = []
        self.response = ""

    def add_route(self, path, handler, method="GET"):
        self.routes.append((method, path, handler))

    def send(self, data):
        self.response += data.decode() if isinstance(data, bytes) else data


class Service:
    def read(self, samples):
        return {"samples": samples, "millimetres": 125}


class ManifestRestApiTest(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer()
        self.api = ManifestRestApi(self.server, MANIFEST, Service())

    def body(self):
        return json.loads(self.server.response.split("\r\n\r\n", 1)[1])

    def test_registers_manifest_and_declared_operation(self):
        routes = [(method, path) for method, path, _ in self.server.routes]
        self.assertIn(("GET", "/manifest"), routes)
        self.assertIn(("POST", "/api/distance/read"), routes)

    def test_invokes_declared_method_with_coerced_arguments(self):
        request = 'POST /api/distance/read HTTP/1.1\r\nContent-Type: application/json\r\n\r\n{"samples":"3"}'
        self.api.invoke("read", request)
        self.assertEqual(self.body()["result"], {"samples": 3, "millimetres": 125})

    def test_rejects_unknown_arguments(self):
        request = 'POST /api/distance/read HTTP/1.1\r\n\r\n{"samples":1,"oops":2}'
        self.api.invoke("read", request)
        self.assertFalse(self.body()["ok"])
        self.assertIn("unknown arguments", self.body()["error"])


if __name__ == "__main__":
    unittest.main()
