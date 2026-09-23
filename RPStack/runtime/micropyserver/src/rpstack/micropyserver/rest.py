"""Node discovery, background operations and out-of-band lifecycle controls."""
from .http import json_body, query_arguments, send_json
from .server import MicroPyServer
from rpstack.primitive_runtime.supervisor import BusyError, LifecycleError, _validate_arguments


class NodeRestApi:
    def __init__(self, node, host="0.0.0.0", port=80, **config):
        self.node = node
        self.server = MicroPyServer(host, port, tasks=node.tasks, **config)
        routes = {
            ("GET", "/manifest"): self.manifest,
            ("GET", "/api/tasks"): self.tasks,
            ("GET", "/api/task"): self.task,
            ("POST", "/api/task/cancel"): self.cancel,
            ("GET", "/api/node/status"): self.status,
            ("POST", "/api/node/stop"): self.stop_node,
            ("POST", "/api/node/reset"): self.reset_node,
            ("POST", "/api/events"): self.event,
            ("POST", "/api/flows/start"): self.flow,
        }
        for service_id, service in node.discovery()["services"].items():
            for name, operation in service["operations"].items():
                routes[("POST", operation["rest"]["path"])] = self.operation(service_id, name, operation)
        for (method, path), handler in routes.items():
            self.server.add_route(path, self._guard(handler), method)

    def _guard(self, handler):
        async def guarded(request, response):
            try:
                await handler(request, response)
            except BusyError as error:
                send_json(response, {"ok": False, "error": str(error)}, 409)
            except KeyError as error:
                send_json(response, {"ok": False, "error": str(error)}, 404)
            except (ValueError, TypeError, LifecycleError) as error:
                send_json(response, {"ok": False, "error": str(error)}, 422)
            except Exception as error:
                send_json(response, {"ok": False, "error": str(error)}, 500)
        return guarded

    def operation(self, service_id, name, operation):
        async def invoke(request, response):
            args = _validate_arguments(name, operation, json_body(request))
            if operation.get("control") == "stop":
                await self.node.stop()
                send_json(response, {"ok": True, "state": self.node.state})
            elif operation.get("snapshot"):
                send_json(response, {"ok": True, "result": _json_value(await self.node.status(service_id))})
            else:
                task_id = self.node.submit(service_id, name, args)
                send_json(response, {"ok": True, "task_id": task_id, "state": "pending",
                                     "status_url": "/api/task?id={}".format(task_id)}, 202)
        return invoke

    async def manifest(self, request, response):
        send_json(response, self.node.discovery())

    async def tasks(self, request, response):
        send_json(response, {"tasks": _json_value(self.node.tasks.snapshot(True))})

    async def task(self, request, response):
        task_id = int(query_arguments(request)["id"])
        send_json(response, _json_value(self.node.tasks.describe(task_id)))

    async def cancel(self, request, response):
        task_id = int(json_body(request)["id"])
        record = self.node.tasks.records[task_id]
        if record["kind"] not in ("flow", "operation"):
            raise ValueError("use node stop for services")
        await self.node.tasks.cancel(task_id)
        send_json(response, {"ok": True})

    async def status(self, request, response):
        send_json(response, {"state": self.node.state, "accepting": self.node.accepting})

    async def stop_node(self, request, response):
        await self.node.stop()
        send_json(response, {"ok": True, "state": self.node.state})

    async def reset_node(self, request, response):
        await self.node.reset()
        send_json(response, {"ok": True, "state": self.node.state})

    async def event(self, request, response):
        args = json_body(request)
        self.node.engine.events.publish(args["name"], args.get("payload"))
        send_json(response, {"ok": True})

    async def flow(self, request, response):
        task_id = self.node.start_flow(json_body(request)["name"])
        send_json(response, {"ok": True, "task_id": task_id,
                             "status_url": "/api/task?id={}".format(task_id)}, 202)

    async def start(self):
        await self.server.start()

    async def run(self):
        await self.server.run()

    async def stop(self):
        await self.server.stop()


def _json_value(value):
    if hasattr(value, "as_dict"):
        return _json_value(value.as_dict())
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
