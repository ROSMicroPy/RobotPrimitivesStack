import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path
for runtime_src in Path(__file__).resolve().parents[2].glob("*/src"):
    sys.path.insert(0, str(runtime_src))

from rpstack.micropyserver.utils import (
    create_cookie,
    get_cookies,
    get_request_post_params,
    get_request_query_params,
    unquote,
)


class UtilsTest(unittest.TestCase):
    def test_query_arguments(self):
        request = "GET /?first=one&second=two HTTP/1.1\r\n\r\n"
        self.assertEqual(get_request_query_params(request), {"first": "one", "second": "two"})

    def test_form_post_arguments(self):
        request = "POST / HTTP/1.1\r\nContent-Length: 7\r\n\r\none=two"
        self.assertEqual(get_request_post_params(request), {"one": "two"})

    def test_unicode_unquote(self):
        self.assertEqual(unquote("hello%20world"), "hello world")

    def test_cookies(self):
        request = "GET / HTTP/1.1\r\nCookie: first=one; second=two\r\n\r\n"
        self.assertEqual(get_cookies(request), {"first": "one", "second": "two"})
        self.assertEqual(
            create_cookie("name", "value", expires="Sat, 01-Jan-2030 00:00:00 GMT"),
            "Set-Cookie: name=value; path=/; expires=Sat, 01-Jan-2030 00:00:00 GMT",
        )


if __name__ == "__main__":
    unittest.main()
