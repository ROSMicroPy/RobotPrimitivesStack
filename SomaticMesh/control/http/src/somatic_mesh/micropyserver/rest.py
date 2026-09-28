"""Node discovery, background operations and out-of-band lifecycle controls."""
from .http import json_body, query_arguments, send_json
from .server import MicroPyServer
from somatic_mesh.fabric_node.supervisor import BusyError, LifecycleError, _validate_arguments


class FabricRestApi:
    # Expose node controls and manifest-declared service operations through guarded HTTP routes.
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
            ("POST", "/api/node/calibrate"): self.calibrate_node,
            ("POST", "/api/signals"): self.signal,
            ("GET", "/api/execution"): self.execution,
            ("POST", "/api/flows/start"): self.flow,
        }
        for service_id, service in node.discovery()["services"].items():
            for name, operation in service["operations"].items():
                routes[("POST", operation["rest"]["path"])] = self.operation(service_id, name, operation)
        for (method, path), handler in routes.items():
            self.server.add_route(path, self._guard(handler), method)

    # Wrap a handler in consistent JSON error responses.
    def _guard(self, handler):
        # Map busy, missing, invalid, and unexpected failures to their HTTP status codes.
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

    # Build a handler bound to one service operation and its manifest metadata.
    def operation(self, service_id, name, operation):
        # Validate arguments, serve immediate controls/snapshots, or return an accepted task ID.
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

    # Return the node's public discovery document.
    async def manifest(self, request, response):
        send_json(response, self.node.discovery())

    # Return retained managed tasks with transport-compatible results.
    async def tasks(self, request, response):
        send_json(response, {"tasks": _json_value(self.node.tasks.snapshot(True))})

    # Look up and serialize the task selected by the query ID.
    async def task(self, request, response):
        task_id = int(query_arguments(request)["id"])
        send_json(response, _json_value(self.node.tasks.describe(task_id)))

    # Cancel a flow or operation while protecting resident service tasks from this endpoint.
    async def cancel(self, request, response):
        task_id = int(json_body(request)["id"])
        record = self.node.tasks.records[task_id]
        if record["kind"] not in ("flow", "operation"):
            raise ValueError("use node stop for services")
        await self.node.tasks.cancel(task_id)
        send_json(response, {"ok": True})

    # Report node lifecycle state, admission status, and calibration progress.
    async def status(self, request, response):
        send_json(response, {"state": self.node.state, "accepting": self.node.accepting,
                             "calibration": _json_value(self.node.calibration_status())})

    # Validate a calibration request and return a task URL for asynchronous progress.
    async def calibrate_node(self, request, response):
        args = json_body(request)
        if not isinstance(args, dict) or set(args) - {'service', 'arguments'}:
            raise ValueError('expected service and/or arguments')
        service = args.get('service')
        if service is not None and not isinstance(service, str):
            raise ValueError('service must be a string')
        task_id = self.node.submit_calibration(service, args.get('arguments'))
        send_json(response, {'ok': True, 'task_id': task_id, 'state': 'pending',
                             'status_url': '/api/task?id={}'.format(task_id)}, 202)

    # Stop node services and return the resulting lifecycle state.
    async def stop_node(self, request, response):
        await self.node.stop()
        send_json(response, {"ok": True, "state": self.node.state})

    # Rebuild node services and return the resulting lifecycle state.
    async def reset_node(self, request, response):
        await self.node.reset()
        send_json(response, {"ok": True, "state": self.node.state})

    # Return local and remote workflow execution diagnostics.
    async def execution(self, request, response):
        send_json(response, self.node.execution_status())

    # Publish an application signal from its JSON envelope and return the accepted signal.
    async def signal(self, request, response):
        args = json_body(request)
        signal = self.node.publish_signal(args['name'], args.get('payload'),
            correlation=args.get('correlation'), target=args.get('target', '*'),
            routes=args.get('routes'), ttl_ms=args.get('ttl_ms', 10000), hops=args.get('hops', 8))
        send_json(response, {'ok': True, 'signal': signal})

    # Start a named workflow and return its task, run identity, and status URL.
    async def flow(self, request, response):
        task_id = self.node.start_flow(json_body(request)["name"])
        send_json(response, {"ok": True, "task_id": task_id,
                             "run_id": self.node.engine.runs[task_id]["run_id"],
                             "status_url": "/api/task?id={}".format(task_id)}, 202)

    # Start the HTTP listener as part of runtime startup.
    async def start(self):
        await self.server.start()

    # Keep the REST service resident through the server's run hook.
    async def run(self):
        await self.server.run()

    # Stop HTTP acceptance and release active server requests.
    async def stop(self):
        await self.server.stop()


# Recursively turn samples and nested containers into JSON-friendly response values.
def _json_value(value):
    if hasattr(value, "as_dict"):
        return _json_value(value.as_dict())
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
