"""Request parsing and response helpers with no CPython-only dependencies."""

try:
    import ujson as json
except ImportError:
    import json


HTTP_REASONS = {
    200: "OK", 202: "Accepted", 409: "Conflict", 204: "No Content", 400: "Bad Request", 404: "Not Found",
    405: "Method Not Allowed", 422: "Unprocessable Entity",
    500: "Internal Server Error",
}


def request_method(request):
    return request.split(" ", 1)[0].upper()


def request_target(request):
    return request.split(" ", 2)[1]


def request_body(request):
    parts = request.split("\r\n\r\n", 1)
    return parts[1] if len(parts) == 2 else ""


def json_body(request):
    body = request_body(request)
    return json.loads(body) if body else {}


def query_arguments(request):
    target = request_target(request)
    if "?" not in target:
        return {}
    result = {}
    for item in target.split("?", 1)[1].split("&"):
        if not item:
            continue
        pair = item.split("=", 1)
        result[unquote(pair[0])] = unquote(pair[1] if len(pair) == 2 else "")
    return result


def unquote(value):
    value = value.replace("+", " ")
    raw = value.encode("utf-8")
    pieces = raw.split(b"%")
    if len(pieces) == 1:
        return value
    output = bytearray(pieces[0])
    for piece in pieces[1:]:
        try:
            output.append(int(piece[:2], 16))
            output.extend(piece[2:])
        except (ValueError, IndexError):
            output.extend(b"%")
            output.extend(piece)
    return bytes(output).decode("utf-8")


def send_json(server, value, status=200, extra_headers=None):
    body = json.dumps(value)
    headers = [
        "HTTP/1.0 {} {}".format(status, HTTP_REASONS.get(status, "")),
        "Content-Type: application/json",
        "Content-Length: {}".format(len(body.encode("utf-8"))),
        "Access-Control-Allow-Origin: *",
        "Access-Control-Allow-Headers: Content-Type",
        "Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS",
    ]
    if extra_headers:
        headers.extend(extra_headers)
    server.send("\r\n".join(headers) + "\r\n\r\n" + body)
