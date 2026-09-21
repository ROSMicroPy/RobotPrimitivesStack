"""Lifecycle supervision and declared-operation dispatch."""

from .manifest import load_entry_point
from .registry import CapabilityRegistry, ResolutionError, ServiceDefinition


class LifecycleError(RuntimeError):
    pass


class ServiceSupervisor:
    def __init__(self):
        self.registry = CapabilityRegistry()
        self._start_order = []
        self._started = []

    def register(self, service_id, manifest, factory=None, config=None,
                 bindings=None, implementation=None):
        definition = ServiceDefinition(
            service_id, manifest, factory, config, bindings, implementation
        )
        self.registry.register(definition)
        return definition

    def prepare(self):
        self._start_order = self.registry.resolve()
        for service_id in self._start_order:
            definition = self.registry.get(service_id)
            dependency_instances = {}
            for role, dependency_id in definition.dependencies.items():
                dependency_instances[role] = self.registry.get(dependency_id).instance
            factory = definition.factory
            if factory is None:
                factory = load_entry_point(definition.manifest.entry_point)
            definition.instance = factory(**dependency_instances)
            self._call_lifecycle(definition, "configure", definition.config)
            self._call_lifecycle(definition, "init")
        return list(self._start_order)

    def start(self):
        if not self._start_order:
            self.prepare()
        try:
            for service_id in self._start_order:
                definition = self.registry.get(service_id)
                self._call_lifecycle(definition, "start")
                self._started.append(service_id)
        except Exception:
            self.stop()
            raise
        return list(self._started)

    def stop(self):
        success = True
        for service_id in reversed(self._started):
            definition = self.registry.get(service_id)
            try:
                result = self._call_lifecycle(definition, "stop")
                if result is False:
                    success = False
            except Exception:
                success = False
        self._started = []
        return success

    def restart(self, service_id):
        definition = self.registry.get(service_id)
        self._call_lifecycle(definition, "stop")
        reset_method = definition.manifest.lifecycle.get("reset")
        if reset_method:
            self._call_lifecycle(definition, "reset")
        else:
            self._call_lifecycle(definition, "init")
        return self._call_lifecycle(definition, "start")

    def status(self, service_id):
        definition = self.registry.get(service_id)
        return self._call_lifecycle(definition, "status")

    def instance(self, service_id):
        definition = self.registry.get(service_id)
        if definition.instance is None:
            raise LifecycleError("service {} is not prepared".format(service_id))
        return definition.instance

    def invoke(self, service_id, operation_name, arguments=None):
        definition = self.registry.get(service_id)
        operation = definition.manifest.operation(operation_name)
        implementations = operation.get("implementations")
        if implementations is not None and definition.implementation not in implementations:
            raise LifecycleError(
                "operation {} is unavailable for implementation {}".format(
                    operation_name, definition.implementation
                )
            )
        arguments = arguments or {}
        _validate_arguments(operation_name, operation, arguments)
        method = getattr(self.instance(service_id), operation["method"])
        return method(**arguments)

    def _call_lifecycle(self, definition, stage, *arguments):
        method_name = definition.manifest.lifecycle.get(stage)
        if not method_name:
            return True
        method = getattr(definition.instance, method_name)
        result = method(*arguments)
        if result is False:
            raise LifecycleError(
                "{} lifecycle {} failed".format(definition.service_id, stage)
            )
        return result


def _validate_arguments(operation_name, operation, arguments):
    declared = operation.get("arguments", {})
    unknown = [name for name in arguments if name not in declared]
    if unknown:
        raise LifecycleError(
            "operation {} received undeclared arguments: {}".format(
                operation_name, ", ".join(unknown)
            )
        )
    missing = [
        name for name, specification in declared.items()
        if specification.get("required", False) and name not in arguments
    ]
    if missing:
        raise LifecycleError(
            "operation {} is missing arguments: {}".format(
                operation_name, ", ".join(missing)
            )
        )
