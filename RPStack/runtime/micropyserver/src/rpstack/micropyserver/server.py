"""Async HTTP server with connection-local responses and bounded requests."""
from rpstack.execution_engine import TaskRegistry, asyncio, call


class Response:
    def __init__(self, writer):
        self.writer = writer

    def send(self, data):
        self.writer.write(data.encode("utf-8") if isinstance(data, str) else data)


class MicroPyServer:
    def __init__(self, host="0.0.0.0", port=80, request_limit=16384,
                 request_timeout_s=5, tasks=None, max_clients=8):
        self.host, self.port = host, port
        self.request_limit, self.request_timeout_s = request_limit, request_timeout_s
        self.tasks = tasks or TaskRegistry()
        self.max_clients = max_clients
        self.routes = []
        self.server = None
        self.clients = set()

    def add_route(self, path, handler, method="GET"):
        self.routes.append((method.upper(), path, handler))

    async def start(self):
        self.server = await asyncio.start_server(self._accept, self.host, self.port)

    async def run(self):
        await asyncio.Event().wait()

    async def _accept(self, reader, writer):
        if len(self.clients) >= self.max_clients:
            writer.close()
            await writer.wait_closed()
            return
        try:
            task_id = self.tasks.spawn("http:request", self._client, reader, writer, kind="request")
        except RuntimeError:
            writer.close()
            await writer.wait_closed()
            return
        self.clients.add(task_id)
        try:
            await self.tasks.wait(task_id)
        finally:
            self.clients.discard(task_id)

    async def _read(self, reader):
        data = b""
        total = None
        while total is None or len(data) < total:
            chunk = await reader.read(min(512, self.request_limit - len(data)))
            if not chunk:
                raise ValueError("incomplete request")
            data += chunk
            header_end = data.find(b"\r\n\r\n")
            if header_end >= 0 and total is None:
                headers = data[:header_end].decode("utf-8")
                if "transfer-encoding:" in headers.lower():
                    raise ValueError("Transfer-Encoding is unsupported")
                total = header_end + 4 + _content_length(headers)
                if total > self.request_limit:
                    raise ValueError("request too large")
            if len(data) >= self.request_limit and (total is None or len(data) < total):
                raise ValueError("request too large")
        return data[:total].decode("utf-8")

    async def _client(self, reader, writer):
        from .http import send_json
        response = Response(writer)
        try:
            request = await asyncio.wait_for(self._read(reader), self.request_timeout_s)
            method, path = request_line(request)
            if method == "OPTIONS":
                send_json(response, {}, 204)
            else:
                for route_method, route_path, handler in self.routes:
                    if method == route_method and path == route_path:
                        await call(handler, request, response)
                        break
                else:
                    send_json(response, {"ok": False, "error": "not found"}, 404)
            await asyncio.wait_for(writer.drain(), self.request_timeout_s)
        except (ValueError, asyncio.TimeoutError) as error:
            send_json(response, {"ok": False, "error": str(error)}, 400)
            await asyncio.wait_for(writer.drain(), self.request_timeout_s)
        finally:
            writer.close()
            await writer.wait_closed()

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        for task_id in tuple(self.clients):
            if task_id in self.tasks.records:
                await self.tasks.cancel(task_id)


def _content_length(headers):
    length = 0
    seen = False
    for line in headers.split("\r\n")[1:]:
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() == "content-length":
            if seen:
                raise ValueError("duplicate Content-Length")
            seen = True
            length = int(value.strip())
            if length < 0:
                raise ValueError("negative Content-Length")
    return length


def request_line(request):
    parts = request.split("\r\n", 1)[0].split()
    if len(parts) != 3:
        raise ValueError("invalid HTTP request line")
    return parts[0].upper(), parts[1].split("?", 1)[0]
