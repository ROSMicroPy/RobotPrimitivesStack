import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path
for runtime_src in Path(__file__).resolve().parents[2].glob("*/src"):
    sys.path.insert(0, str(runtime_src))

from rpstack.micropyserver.server import MicroPyServer, _content_length, request_line


class FakeConnection:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    async def read(self, _):
        return self.chunks.pop(0) if self.chunks else b""


class ServerParsingTest(unittest.IsolatedAsyncioTestCase):
    async def test_content_length_is_case_insensitive(self):
        headers = "POST / HTTP/1.1\r\ncontent-length: 7"
        self.assertEqual(_content_length(headers), 7)

    async def test_reads_body_split_across_packets(self):
        server = MicroPyServer()
        reader = FakeConnection([
            b"POST /api HTTP/1.1\r\nContent-Length: 7\r\n\r\none=",
            b"two",
        ])
        self.assertTrue((await server._read(reader)).endswith("one=two"))

    async def test_request_line_drops_query_string(self):
        request = "GET /manifest?x=1 HTTP/1.1\r\n\r\n"
        self.assertEqual(request_line(request), ("GET", "/manifest"))

    async def test_rejects_duplicate_and_oversize_lengths(self):
        with self.assertRaises(ValueError):
            _content_length("POST / HTTP/1.1\r\nContent-Length: 1\r\nContent-Length: 2")
        reader = FakeConnection([b"POST / HTTP/1.1\r\nContent-Length: 99999\r\n\r\n"])
        with self.assertRaisesRegex(ValueError, "too large"):
            await MicroPyServer()._read(reader)


if __name__ == "__main__":
    unittest.main()
