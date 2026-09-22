import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rpstack.micropyserver import ManifestRestApi


MANIFEST = {
    "manifest": "rp.service/v1",
    "service": {
        "name": "linear-slide",
        "operations": {
            "position": {
                "method": "position",
                "arguments": {},
                "rest": {"method": "GET", "path": "/api/linear-slide/position"},
            },
            "move": {
                "method": "move",
                "arguments": {"target": {"type": "number", "required": True}},
                "rest": {"method": "POST", "path": "/api/linear-slide/move-to"},
            },
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


class Sample:
    def as_dict(self):
        return {"kind": "linear", "value": 0.125, "unit": "m"}


class Service:
    def position(self):
        return Sample()

    def move(self, target):
        return {"target": target, "sample": Sample()}


class SerializationTest(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer()
        self.api = ManifestRestApi(self.server, MANIFEST, Service())

    def body(self):
        return json.loads(self.server.response.split("\r\n\r\n", 1)[1])

    def test_serializes_measurement_objects(self):
        self.api.invoke("position", "GET /api/linear-slide/position HTTP/1.1\r\n\r\n")
        self.assertEqual(
            self.body()["result"],
            {"kind": "linear", "value": 0.125, "unit": "m"},
        )

    def test_serializes_nested_measurements_and_coerces_numbers(self):
        request = (
            'POST /api/linear-slide/move-to HTTP/1.1\r\n'
            'Content-Type: application/json\r\n\r\n{"target":"0.2"}'
        )
        self.api.invoke("move", request)
        self.assertEqual(self.body()["result"]["target"], 0.2)
        self.assertEqual(self.body()["result"]["sample"]["unit"], "m")


if __name__ == "__main__":
    unittest.main()
