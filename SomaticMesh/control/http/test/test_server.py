import os
from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest



from somatic_mesh.micropyserver.server import MicroPyServer, _content_length, request_line


class FakeConnection:
    # Prepare network chunks to simulate a fragmented incoming request.
    def __init__(self, chunks):
        self.chunks = list(chunks)

    # Return the next scripted chunk, then EOF when input is exhausted.
    async def read(self, _):
        return self.chunks.pop(0) if self.chunks else b""


class ServerParsingTest(unittest.IsolatedAsyncioTestCase):
    # Check that lowercase Content-Length is accepted.
    async def test_content_length_is_case_insensitive(self):
        headers = "POST / HTTP/1.1\r\ncontent-length: 7"
        self.assertEqual(_content_length(headers), 7)

    # Verify request-body assembly continues across separate network reads.
    async def test_reads_body_split_across_packets(self):
        server = MicroPyServer()
        reader = FakeConnection([
            b"POST /api HTTP/1.1\r\nContent-Length: 7\r\n\r\none=",
            b"two",
        ])
        self.assertTrue((await server._read(reader)).endswith("one=two"))

    # Ensure route matching uses the path without query parameters.
    async def test_request_line_drops_query_string(self):
        request = "GET /manifest?x=1 HTTP/1.1\r\n\r\n"
        self.assertEqual(request_line(request), ("GET", "/manifest"))

    # Reject ambiguous length headers and bodies larger than the request limit.
    async def test_rejects_duplicate_and_oversize_lengths(self):
        with self.assertRaises(ValueError):
            _content_length("POST / HTTP/1.1\r\nContent-Length: 1\r\nContent-Length: 2")
        reader = FakeConnection([b"POST / HTTP/1.1\r\nContent-Length: 99999\r\n\r\n"])
        with self.assertRaisesRegex(ValueError, "too large"):
            await MicroPyServer()._read(reader)


if __name__ == "__main__":
    unittest.main()
