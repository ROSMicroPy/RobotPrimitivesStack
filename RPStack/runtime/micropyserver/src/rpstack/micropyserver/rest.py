"""Expose an rp.service/v1 manifest and its allow-listed operations over REST."""

try:
    import ujson as json
except ImportError:
    import json

from .http import json_body, query_arguments, request_method, send_json


class RestError(ValueError):
    pass


class ManifestRestApi:
    """Bind one service instance to routes declared by its service manifest."""

    def __init__(self, server, manifest, service, manifest_path="/manifest"):
        document = getattr(manifest, "document", manifest)
        if not isinstance(document, dict) or document.get("manifest") != "rp.service/v1":
            raise RestError("expected an rp.service/v1 manifest")
        self.server = server
        self.manifest = document
        self.service = service
        self.manifest_path = manifest_path
        self.routes = {}
        self._bind()

    def _bind(self):
        self.server.add_route(self.manifest_path, self._serve_manifest, "GET")
        self.server.add_route(self.manifest_path, self._serve_options, "OPTIONS")
        operations = self.manifest.get("service", {}).get("operations", {})
        for name, operation in operations.items():
            rest = operation.get("rest", {})
            path = rest.get("path", "/api/operations/{}".format(name))
            method = rest.get("method", "POST").upper()
            self.routes[name] = {"path": path, "method": method, "operation": operation}
            self.server.add_route(path, self._handler(name), method)
            self.server.add_route(path, self._serve_options, "OPTIONS")

    def _handler(self, operation_name):
        def handle(request):
            self.invoke(operation_name, request)
        return handle

    def _serve_manifest(self, request):
        send_json(self.server, self.manifest)

    def _serve_options(self, request):
        send_json(self.server, {}, 204)

    def invoke(self, operation_name, request):
        operation = self.routes[operation_name]["operation"]
        try:
            arguments = query_arguments(request) if request_method(request) == "GET" else json_body(request)
            arguments = _coerce_arguments(arguments, operation.get("arguments", {}))
            result = getattr(self.service, operation["method"])(**arguments)
            send_json(self.server, {"ok": True, "operation": operation_name, "result": _json_value(result)})
        except (ValueError, TypeError, KeyError) as error:
            send_json(self.server, {"ok": False, "operation": operation_name, "error": str(error)}, 422)
        except Exception as error:
            send_json(self.server, {"ok": False, "operation": operation_name, "error": str(error)}, 500)



def _json_value(value):
    as_dict = getattr(value, "as_dict", None)
    if as_dict is not None:
        return _json_value(as_dict())
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value

def _coerce_arguments(values, schema):
    if not isinstance(values, dict):
        raise ValueError("request body must be a JSON object")
    unknown = [name for name in values if name not in schema]
    if unknown:
        raise ValueError("unknown arguments: {}".format(", ".join(unknown)))
    result = {}
    for name, definition in schema.items():
        if name not in values:
            if definition.get("required"):
                raise ValueError("{} is required".format(name))
            if "default" in definition:
                result[name] = definition["default"]
            continue
        value = values[name]
        kind = definition.get("type")
        if kind == "integer":
            value = int(value)
        elif kind == "number":
            value = float(value)
        elif kind == "boolean" and isinstance(value, str):
            value = value.lower() in ("1", "true", "yes", "on")
        elif kind in ("object", "i2c_ref", "pin_ref") and isinstance(value, str):
            value = json.loads(value)
        result[name] = value
    return result
