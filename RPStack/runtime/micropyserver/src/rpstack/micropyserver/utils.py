"""Compatibility helpers from the original MicroPyServer package."""

import re

from .http import HTTP_REASONS, request_method, query_arguments, send_json, unquote


def send_response(server, response, http_code=200, content_type="text/html", extend_headers=None):
    body = str(response)
    headers = [
        "HTTP/1.0 {} {}".format(http_code, HTTP_REASONS.get(http_code, "")),
        "Content-Type: {}".format(content_type),
        "Content-Length: {}".format(len(body.encode("utf-8"))),
    ]
    if extend_headers:
        headers.extend(extend_headers)
    server.send("\r\n".join(headers) + "\r\n\r\n" + body)


def get_request_method(request):
    return request_method(request)


def get_request_query_string(request):
    first_line = request.split("\r\n", 1)[0]
    match = re.search(r"\?([^\s]*)", first_line)
    return match.group(1) if match else ""


def parse_query_string(query_string):
    if not query_string:
        return {}
    request = "GET /?{} HTTP/1.1\r\n\r\n".format(query_string)
    return query_arguments(request)


def get_request_query_params(request):
    return query_arguments(request)


def get_request_post_params(request):
    if request_method(request) != "POST":
        return None
    parts = request.split("\r\n\r\n", 1)
    return parse_query_string(parts[1] if len(parts) == 2 else "")


def get_cookies(request):
    for line in request.split("\r\n")[1:]:
        if ":" not in line:
            continue
        header, value = line.split(":", 1)
        if header.strip().lower() == "cookie":
            cookies = {}
            for cookie in value.strip().split(";"):
                name, cookie_value = cookie.strip().split("=", 1)
                cookies[name] = cookie_value
            return cookies
    return {}


def create_cookie(name, value, path="/", domain=None, expires=None):
    cookie = "Set-Cookie: {}={}".format(name, value)
    if path:
        cookie += "; path=" + path
    if domain:
        cookie += "; domain=" + domain
    if expires:
        cookie += "; expires=" + expires
    return cookie


__all__ = (
    "send_response", "send_json", "get_request_method",
    "get_request_query_string", "parse_query_string",
    "get_request_query_params", "get_request_post_params", "unquote",
    "get_cookies", "create_cookie",
)
