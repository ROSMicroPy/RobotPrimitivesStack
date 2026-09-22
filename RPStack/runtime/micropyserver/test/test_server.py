import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rpstack.micropyserver.server import MicroPyServer, _content_length, request_line


class FakeConnection:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def recv(self, _):
        return self.chunks.pop(0) if self.chunks else b""


class ServerParsingTest(unittest.TestCase):
    def test_content_length_is_case_insensitive(self):
        headers = "POST / HTTP/1.1\r\ncontent-length: 7"
        self.assertEqual(_content_length(headers), 7)

    def test_reads_body_split_across_packets(self):
        server = MicroPyServer()
        server._connect = FakeConnection([
            b"POST /api HTTP/1.1\r\nContent-Length: 7\r\n\r\none=",
            b"two",
        ])
        self.assertTrue(server.get_request().endswith("one=two"))

    def test_request_line_drops_query_string(self):
        request = "GET /manifest?x=1 HTTP/1.1\r\n\r\n"
        self.assertEqual(request_line(request), ("GET", "/manifest"))

    def test_routes_are_exact_static_paths(self):
        server = MicroPyServer()
        handler = lambda _: None
        server.add_route("/manifest", handler)
        route = server.find_route("GET /manifest HTTP/1.1\r\n\r\n")
        self.assertIs(route["handler"], handler)
        self.assertIsNone(
            server.find_route("GET /manifest-extra HTTP/1.1\r\n\r\n")
        )


if __name__ == "__main__":
    unittest.main()
