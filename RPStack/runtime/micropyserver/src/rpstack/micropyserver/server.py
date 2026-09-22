"""A deliberately small synchronous HTTP server compatible with MicroPython."""

import io
import socket
import sys


class MicroPyServer:
    def __init__(self, host="0.0.0.0", port=80, request_limit=16384):
        self._host = host
        self._port = port
        self._request_limit = request_limit
        self._routes = []
        self._connect = None
        self._on_request_handler = None
        self._on_not_found_handler = None
        self._on_error_handler = None
        self._sock = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._sock.listen(1)
        print("MicroPyServer listening on {}:{}".format(self._host, self._port))
        while self._sock is not None:
            try:
                self._connect, address = self._sock.accept()
                request = self.get_request()
                if not request:
                    continue
                if self._on_request_handler and not self._on_request_handler(request, address):
                    continue
                route = self.find_route(request)
                if route:
                    route["handler"](request)
                else:
                    self._route_not_found(request)
            except Exception as error:
                self._internal_error(error)
            finally:
                if self._connect is not None:
                    try:
                        self._connect.close()
                    except Exception:
                        pass
                    self._connect = None

    def stop(self):
        if self._connect is not None:
            self._connect.close()
        if self._sock is not None:
            self._sock.close()
        self._sock = None

    def add_route(self, path, handler, method="GET"):
        self._routes.append({"path": path, "handler": handler, "method": method.upper()})

    def send(self, data):
        if self._connect is None:
            raise RuntimeError("cannot send a response without an active connection")
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._connect.sendall(data)

    def find_route(self, request):
        method, path = request_line(request)
        for route in self._routes:
            if method != route["method"]:
                continue
            if path == route["path"]:
                return route
        return None

    def get_request(self):
        chunks = []
        received = 0
        header_end = -1
        content_length = 0
        while received < self._request_limit:
            chunk = self._connect.recv(min(1024, self._request_limit - received))
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
            data = b"".join(chunks)
            if header_end < 0:
                header_end = data.find(b"\r\n\r\n")
                if header_end >= 0:
                    headers = data[:header_end].decode("utf-8")
                    content_length = _content_length(headers)
            if header_end >= 0 and len(data) >= header_end + 4 + content_length:
                break
        return b"".join(chunks).decode("utf-8")

    def on_request(self, handler):
        self._on_request_handler = handler

    def on_not_found(self, handler):
        self._on_not_found_handler = handler

    def on_error(self, handler):
        self._on_error_handler = handler

    def _route_not_found(self, request):
        if self._on_not_found_handler:
            self._on_not_found_handler(request)
        else:
            self.send("HTTP/1.0 404 Not Found\r\nContent-Type: text/plain\r\n\r\nNot found")

    def _internal_error(self, error):
        if self._on_error_handler:
            self._on_error_handler(error)
            return
        if "print_exception" in dir(sys):
            output = io.StringIO()
            sys.print_exception(error, output)
            message = output.getvalue()
            output.close()
        else:
            message = str(error)
        if self._connect is not None:
            self.send("HTTP/1.0 500 Internal Server Error\r\nContent-Type: text/plain\r\n\r\nError: " + message)



def _content_length(headers):
    for line in headers.split("\r\n")[1:]:
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() == "content-length":
            try:
                length = int(value.strip())
            except ValueError:
                raise ValueError("invalid Content-Length header")
            if length < 0:
                raise ValueError("Content-Length cannot be negative")
            return length
    return 0


def request_line(request):
    line = request.split("\r\n", 1)[0]
    parts = line.split()
    if len(parts) < 2:
        raise ValueError("invalid HTTP request line")
    return parts[0].upper(), parts[1].split("?", 1)[0]
