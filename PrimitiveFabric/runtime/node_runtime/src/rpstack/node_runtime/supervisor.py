"""Async lifecycle supervision and resource-aware operation dispatch."""
from rpstack.support import asyncio, call
from rpstack.execution_engine import TaskRegistry
from .manifest import load_entry_point
from .registry import ServiceRegistry, ServiceDefinition


class LifecycleError(RuntimeError):
    pass


class BusyError(LifecycleError):
    pass


class ServiceSupervisor:
    # Prepare service ownership, task tracking, resource claims, and serialized lifecycle
    # control.
    def __init__(self, tasks=None):
        self.registry = ServiceRegistry()
        self.tasks = tasks or TaskRegistry()
        self._start_order = []
        self._prepared = []
        self._started = []
        self._service_tasks = {}
        self._claims = {}
        self._calibration = {}
        self.accepting = False
        self._closing = False
        self.state = "new"
        self._control_lock = asyncio.Lock()

    # Register a service definition and initialize its calibration status.
    def register(self, service_id, manifest, factory=None, config=None,
                 bindings=None, implementation=None):
        definition = ServiceDefinition(service_id, manifest, factory, config, bindings, implementation)
        self.registry.register(definition)
        self._reset_calibration(definition)
        return definition

    # Invoke a manifest-selected lifecycle method and treat an explicit False as failure.
    async def _lifecycle(self, definition, stage, *args):
        method = definition.manifest.lifecycle.get(stage)
        if method:
            result = await call(getattr(definition.instance, method), *args)
            if result is False:
                raise LifecycleError("{} {} failed".format(definition.service_id, stage))
            return result
        return True

    # Construct and initialize services in dependency order, unwinding partial startup on
    # failure.
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
                self._reset_calibration(d)
                self._prepared.append(service_id)
                await self._lifecycle(d, "configure", d.config)
                await self._lifecycle(d, "init")
        except BaseException:
            await self._release()
            raise
        return list(self._start_order)

    # Run a service's resident loop or wait indefinitely, rejecting unexpected loop completion.
    async def _resident(self, definition):
        run = getattr(definition.instance, "run", None)
        if run:
            await call(run)
            raise LifecycleError("service task exited unexpectedly")
        await asyncio.Event().wait()

    # Prepare and start every service before allowing operations; unwind failures consistently.
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

    # Cancel resident tasks and stop/release prepared services in reverse dependency order.
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

    # Provide a subclass hook for invalidating remote work during lifecycle changes.
    def _invalidate_execution(self):
        pass

    # Block new work, cancel operations and flows, then release services under the control lock.
    async def stop(self):
        async with self._control_lock:
            self.accepting = False
            self._invalidate_execution()
            self.state = "stopping"
            await self.tasks.cancel_kinds(("flow", "operation"))
            errors = await self._release()
            self.state = "failed" if errors else "stopped"
            if errors:
                raise LifecycleError("; ".join(errors))
            return True

    # Cancel work and reconstruct services so all implementations follow the same reset path.
    async def reset(self):
        async with self._control_lock:
            if self._closing:
                raise LifecycleError("node is shutting down")
            self.accepting = False
            self._invalidate_execution()
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

    # Read a service's status through its declared lifecycle hook.
    async def status(self, service_id):
        return await self._lifecycle(self.registry.get(service_id), "status")

    # Mark calibration pending only when the service declares a calibration hook.
    def _reset_calibration(self, definition):
        self._calibration[definition.service_id] = {
            'state': 'pending' if definition.manifest.lifecycle.get('calibrate') else 'not_required',
            'result': None, 'error': None,
        }

    # Return copies of per-service calibration states for inspection.
    def calibration_status(self):
        return {name: dict(state) for name, state in self._calibration.items()}

    def submit_calibration(self, service_id=None, arguments=None):
        """Explicit phase; reserve dependencies before running any hook.

        With no service ID, arguments maps service IDs to parameter dictionaries.
        Services without a manifest calibrate hook are reported as not_required.
        """
        if not self.accepting:
            raise BusyError('node is ' + self.state)
        if arguments is not None and not isinstance(arguments, dict):
            raise LifecycleError('calibration arguments must be an object')
        names = [service_id] if service_id is not None else list(self._start_order)
        values = {service_id: arguments or {}} if service_id is not None else (arguments or {})
        if not isinstance(values, dict) or any(name not in names for name in values):
            raise LifecycleError('calibration arguments must name selected services')
        plan, resources = [], set()
        for name in names:
            definition = self.registry.get(name)
            self.instance(name)
            method = definition.manifest.lifecycle.get('calibrate')
            operation = definition.manifest.operations.get('calibrate', {'arguments': {}})
            if method:
                implementations = operation.get('implementations')
                if implementations is not None and definition.implementation not in implementations:
                    raise LifecycleError('calibration unavailable for implementation')
                parameters = _validate_arguments('calibrate', operation, values.get(name, {}))
            else:
                if values.get(name):
                    raise LifecycleError(name + ' has no calibration parameters')
                parameters = {}
            plan.append((name, method, parameters))
            resources.update(self._resources(name))

        # Run planned calibration hooks in order, recording results, cancellation, or failure.
        async def phase():
            results = {}
            for name, method, parameters in plan:
                if method:
                    record = {'state': 'running', 'result': None, 'error': None}
                    self._calibration[name] = record
                    try:
                        result = await call(getattr(self.instance(name), method), **parameters)
                        if result is False:
                            raise LifecycleError(name + ' calibration failed')
                        record.update(state='calibrated', result=result)
                    except asyncio.CancelledError:
                        record.update(state='cancelled', error='calibration cancelled')
                        raise
                    except Exception as error:
                        record.update(state='failed', error=str(error))
                        raise
                results[name] = dict(self._calibration[name])
            if service_id is not None:
                return results[service_id]['result'] if plan[0][1] else results[service_id]
            return results
        return self._submit_managed('calibrate:' + (service_id or 'all'), service_id,
                                    resources, True, phase)

    # Submit calibration and await it, forwarding caller cancellation to the managed task.
    async def calibrate(self, service_id=None, arguments=None):
        task_id = self.submit_calibration(service_id, arguments)
        try:
            return await self.tasks.wait(task_id)
        except asyncio.CancelledError:
            if task_id in self.tasks.records:
                await self.tasks.cancel(task_id)
            raise

    # Return a prepared service instance or explain that preparation is still required.
    def instance(self, service_id):
        instance = self.registry.get(service_id).instance
        if instance is None:
            raise LifecycleError("service is not prepared: " + service_id)
        return instance

    # Collect a service and all transitive dependencies that its operations may claim.
    def _resources(self, service_id):
        result = {service_id}
        for target in self.registry.get(service_id).dependencies.values():
            result.update(self._resources(target))
        return result

    # Validate an exposed operation and reserve its dependencies before scheduling invocation.
    def submit(self, service_id, operation_name, arguments=None):
        definition = self.registry.get(service_id)
        hook = definition.manifest.lifecycle.get('calibrate')
        operation = definition.manifest.operations.get(operation_name, {})
        if hook and (operation_name == 'calibrate' or operation.get('method') == hook):
            return self.submit_calibration(service_id, arguments)
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
        # Invoke the selected service method with already-validated arguments.
        async def execute():
            return await call(getattr(self.instance(service_id), operation["method"]), **arguments)
        return self._submit_managed(service_id + "." + operation_name, service_id,
            self._resources(service_id), operation.get("concurrency", "exclusive") != "read_only", execute)

    # Reserve compatible resource claims synchronously and release them when managed work ends.
    def _submit_managed(self, name, owner, resources, exclusive, function):
        for resource in resources:
            claims = self._claims.get(resource, [])
            if claims and (exclusive or any(flag for _, flag in claims)):
                raise BusyError("resource busy: " + resource)
        # Reserve before scheduling so simultaneous HTTP requests cannot race.
        token = object()
        for resource in resources:
            self._claims.setdefault(resource, []).append((token, exclusive))

        # Run the operation while guaranteeing resource claims are released afterward.
        async def execute():
            try:
                return await call(function)
            finally:
                release()

        # Remove only this operation's reservation token from each resource's claims.
        def release():
            for resource in resources:
                remaining = [(key, flag) for key, flag in self._claims.get(resource, []) if key is not token]
                if remaining:
                    self._claims[resource] = remaining
                else:
                    self._claims.pop(resource, None)
        try:
            return self.tasks.spawn(name, execute, kind="operation", owner=owner)
        except Exception:
            release()
            raise

    # Submit an operation and await its result, forwarding caller cancellation to it.
    async def invoke(self, service_id, operation_name, arguments=None):
        task_id = self.submit(service_id, operation_name, arguments)
        try:
            return await self.tasks.wait(task_id)
        except asyncio.CancelledError:
            if task_id in self.tasks.records:
                await self.tasks.cancel(task_id)
            raise


# Validate declared operation arguments and translate validation errors into lifecycle errors.
def _validate_arguments(name, operation, arguments):
    if not isinstance(arguments, dict):
        raise LifecycleError("arguments must be an object")
    from .validation import validate_values
    try:
        return validate_values(operation.get("arguments", {}), arguments, name)
    except ValueError as error:
        raise LifecycleError(str(error))
