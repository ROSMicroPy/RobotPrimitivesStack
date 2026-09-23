"""Async lifecycle supervision and resource-aware operation dispatch."""
from rpstack.execution_engine import TaskRegistry, asyncio, call
from .manifest import load_entry_point
from .registry import CapabilityRegistry, ServiceDefinition


class LifecycleError(RuntimeError):
    pass


class BusyError(LifecycleError):
    pass


class ServiceSupervisor:
    def __init__(self, tasks=None):
        self.registry = CapabilityRegistry()
        self.tasks = tasks or TaskRegistry()
        self._start_order = []
        self._prepared = []
        self._started = []
        self._service_tasks = {}
        self._claims = {}
        self.accepting = False
        self._closing = False
        self.state = "new"
        self._control_lock = asyncio.Lock()

    def register(self, service_id, manifest, factory=None, config=None,
                 bindings=None, implementation=None):
        definition = ServiceDefinition(service_id, manifest, factory, config, bindings, implementation)
        self.registry.register(definition)
        return definition

    async def _lifecycle(self, definition, stage, *args):
        method = definition.manifest.lifecycle.get(stage)
        if method:
            result = await call(getattr(definition.instance, method), *args)
            if result is False:
                raise LifecycleError("{} {} failed".format(definition.service_id, stage))
            return result
        return True

    async def prepare(self):
        if self._prepared:
            return list(self._start_order)
        self._start_order = self.registry.resolve()
        try:
            for service_id in self._start_order:
                d = self.registry.get(service_id)
                dependencies = {role: self.instance(target) for role, target in d.dependencies.items()}
                factory = d.factory or load_entry_point(d.manifest.entry_point)
                d.instance = factory(**dependencies)
                self._prepared.append(service_id)
                await self._lifecycle(d, "configure", d.config)
                await self._lifecycle(d, "init")
        except BaseException:
            await self._release()
            raise
        return list(self._start_order)

    async def _resident(self, definition):
        run = getattr(definition.instance, "run", None)
        if run:
            await call(run)
            raise LifecycleError("service task exited unexpectedly")
        await asyncio.Event().wait()

    async def start(self):
        if self._closing:
            raise LifecycleError("node is shutting down")
        if self.state == "running":
            return list(self._started)
        self.state = "starting"
        try:
            await self.prepare()
            for service_id in self._start_order:
                d = self.registry.get(service_id)
                await self._lifecycle(d, "start")
                self._started.append(service_id)
                self._service_tasks[service_id] = self.tasks.spawn(
                    "service:" + service_id, self._resident, d, kind="service", owner=service_id)
            self.accepting = True
            self.state = "running"
        except BaseException:
            self.accepting = False
            await self._release()
            self.state = "failed"
            raise
        return list(self._started)

    async def _release(self):
        errors = []
        for service_id in reversed(self._prepared):
            task_id = self._service_tasks.pop(service_id, None)
            if task_id is not None and task_id in self.tasks.records:
                await self.tasks.cancel(task_id)
                self.tasks.records.pop(task_id, None)
            d = self.registry.get(service_id)
            try:
                await self._lifecycle(d, "stop")
            except Exception as error:
                errors.append("{} stop: {}".format(service_id, error))
            shutdown = getattr(d.instance, "shutdown", None)
            if shutdown:
                try:
                    result = await call(shutdown)
                    if result is False:
                        raise LifecycleError("shutdown returned false")
                except Exception as error:
                    errors.append("{} shutdown: {}".format(service_id, error))
        self._prepared = []
        self._started = []
        return errors

    async def stop(self):
        async with self._control_lock:
            self.accepting = False
            self.state = "stopping"
            await self.tasks.cancel_kinds(("flow", "operation"))
            errors = await self._release()
            self.state = "failed" if errors else "stopped"
            if errors:
                raise LifecycleError("; ".join(errors))
            return True

    async def reset(self):
        async with self._control_lock:
            if self._closing:
                raise LifecycleError("node is shutting down")
            self.accepting = False
            self.state = "resetting"
            await self.tasks.cancel_kinds(("flow", "operation"))
            errors = await self._release()
            if errors:
                self.state = "failed"
                raise LifecycleError("; ".join(errors))
            # Reconstruct services instead of invoking divergent reset hooks.
            self.state = "stopped"
            await self.start()
            return True

    async def status(self, service_id):
        return await self._lifecycle(self.registry.get(service_id), "status")

    def instance(self, service_id):
        instance = self.registry.get(service_id).instance
        if instance is None:
            raise LifecycleError("service is not prepared: " + service_id)
        return instance

    def _resources(self, service_id):
        result = {service_id}
        for target in self.registry.get(service_id).dependencies.values():
            result.update(self._resources(target))
        return result

    def submit(self, service_id, operation_name, arguments=None):
        if not self.accepting:
            raise BusyError("node is " + self.state)
        d = self.registry.get(service_id)
        operation = d.manifest.operation(operation_name)
        if operation.get("control"):
            raise LifecycleError("control operations use the control endpoint")
        implementations = operation.get("implementations")
        if implementations is not None and d.implementation not in implementations:
            raise LifecycleError("operation unavailable for implementation")
        arguments = _validate_arguments(operation_name, operation, arguments or {})
        resources = self._resources(service_id)
        exclusive = operation.get("concurrency", "exclusive") != "read_only"
        for resource in resources:
            claims = self._claims.get(resource, [])
            if claims and (exclusive or any(flag for _, flag in claims)):
                raise BusyError("resource busy: " + resource)
        # Reserve before scheduling so simultaneous HTTP requests cannot race.
        token = object()
        for resource in resources:
            self._claims.setdefault(resource, []).append((token, exclusive))

        async def execute():
            try:
                return await call(getattr(self.instance(service_id), operation["method"]), **arguments)
            finally:
                release()

        def release():
            for resource in resources:
                remaining = [(key, flag) for key, flag in self._claims.get(resource, []) if key is not token]
                if remaining:
                    self._claims[resource] = remaining
                else:
                    self._claims.pop(resource, None)
        try:
            return self.tasks.spawn(service_id + "." + operation_name, execute, kind="operation", owner=service_id)
        except Exception:
            release()
            raise

    async def invoke(self, service_id, operation_name, arguments=None):
        task_id = self.submit(service_id, operation_name, arguments)
        try:
            return await self.tasks.wait(task_id)
        except asyncio.CancelledError:
            if task_id in self.tasks.records:
                await self.tasks.cancel(task_id)
            raise


def _validate_arguments(name, operation, arguments):
    if not isinstance(arguments, dict):
        raise LifecycleError("arguments must be an object")
    from .validation import validate_values
    try:
        return validate_values(operation.get("arguments", {}), arguments, name)
    except ValueError as error:
        raise LifecycleError(str(error))
