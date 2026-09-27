"""Load one node manifest; assemble and supervise all declared services."""
from rpstack.support import asyncio, call
from rpstack.execution_engine import ExecutionEngine
from .manifest import ManifestError, ServiceManifest, load_document, load_entry_point
from .supervisor import ServiceSupervisor, BusyError, LifecycleError
from .validation import validate_values
from rpstack.signals import SignalBus
from rpstack.execution_engine.distributed import RemoteActions


class NodeRuntime(ServiceSupervisor):
    # Assemble node services, signals, transports, and execution infrastructure from the
    # deployment document.
    def __init__(self, document, resource_factories=None):
        super().__init__()
        self.document = document
        self.resources = {}
        self.resource_factories = resource_factories or {}
        identity = document.get('identity', {})
        options = document.get('signals', {})
        self.signals = SignalBus(entity=identity.get('entity', 'local'),
            node_id=identity.get('node', 'local'), routes=options.get('routes'),
            bridges=options.get('bridges'), queue_limit=options.get('queue_limit', 16),
            seen_limit=options.get('seen_limit', 512), max_bytes=options.get('max_bytes', 2048))
        self._signal_transports = []
        self._started_transports = []
        for spec in options.get('transports', []):
            factory = load_entry_point(spec['entry_point'])
            transport = factory(self.signals.entity, self.signals.node_id, **spec.get('config', {}))
            self.signals.add_transport(spec['id'], transport, spec.get('relay', False))
            self._signal_transports.append((spec['id'], transport))
        self.signals.validate_configuration()
        execution = document.get('execution')
        self.remote = RemoteActions(self, execution.get('peers', []), execution.get('expose', []),
            execution.get('lease_ms', 3000), execution.get('capacity', 64)) if execution else None
        self.engine = ExecutionEngine(self.tasks, self.invoke, self.signals, self.remote)
        self._runtime_instances = []
        self.runtime_instances = {}
        self.apps = {}
        self._app_instances = []
        self._runtime_tasks = []
        self._oneshot_tasks = set()
        self._closed = asyncio.Event()
        self._validate_and_register()

    # Read a deployment document and construct its node runtime.
    @classmethod
    def load(cls, path, **kwargs):
        return cls(load_document(path), **kwargs)

    # Validate deployment references and register factories, services, and runtime components.
    def _validate_and_register(self):
        doc = self.document
        if doc.get("manifest") != "rp.node/v1":
            raise ManifestError("expected rp.node/v1")
        if not isinstance(doc.get("services"), dict):
            raise ManifestError("node requires services")
        catalog = doc.get("components", {})
        resources = doc.get("resources", {})
        # Walk nested configuration and reject references to undeclared hardware resources.
        def check_refs(value):
            if isinstance(value, dict):
                if "$resource" in value:
                    if len(value) != 1 or value["$resource"] not in resources:
                        raise ManifestError("unknown resource reference")
                else:
                    for item in value.values():
                        check_refs(item)
            elif isinstance(value, list):
                for item in value:
                    check_refs(item)
        for service_id, spec in doc["services"].items():
            if spec.get("component") not in catalog:
                raise ManifestError("unknown component: " + service_id)
            manifest = ServiceManifest(catalog[spec["component"]])
            implementation = spec.get("implementation")
            selected = manifest.implementation(implementation)
            constructor = spec.get("constructor", {})
            config = spec.get("config", {})
            schema = dict(manifest.configuration)
            schema.update(selected.get("configuration", {}))
            values = dict(constructor)
            values.update(config)
            values = validate_values(schema, values, service_id)
            check_refs(values)
            # Resolve imports before touching any physical resources.
            factory = load_entry_point(manifest.entry_point)
            driver = load_entry_point(selected["entry_point"]) if implementation else None
            # Capture each service's constructor and driver choices without late-binding loop
            # variables.
            def build_factory(factory=factory, driver=driver, constructor=constructor, inject_signals=spec.get("inject_signals", False)):
                # Resolve resources and inject dependencies, optional signals, and a fresh
                # hardware driver.
                def build(**dependencies):
                    args = self._resolve(constructor)
                    args.update(dependencies)
                    if inject_signals:
                        args["signals"] = self.signals
                    if driver:
                        args["driver"] = driver()
                    return factory(**args)
                return build
            definition = self.register(service_id, manifest, build_factory(), values,
                                       spec.get("bindings"), implementation)
            definition.raw_config = values
        self.registry.resolve()
        self._runtime_factories = []
        runtime_names = set()
        for spec in doc.get("runtime", []):
            if not spec.get("id") or spec["id"] in runtime_names:
                raise ManifestError("runtime ids must be unique")
            runtime_names.add(spec["id"])
            self._runtime_factories.append((spec, load_entry_point(spec["entry_point"])))
        self._app_factories = []
        app_names = set()
        for spec in doc.get("apps", []):
            name = spec.get("id")
            if not isinstance(name, str) or not name or name in app_names:
                raise ManifestError("app ids must be unique nonempty strings")
            if spec.get("mode", "resident") not in ("resident", "oneshot"):
                raise ManifestError("app mode must be resident or oneshot")
            dependencies = spec.get("requires", [])
            if not isinstance(dependencies, list) or any(dep not in runtime_names and dep not in app_names for dep in dependencies):
                raise ManifestError("app dependencies must name runtime services or earlier apps")
            if name in runtime_names:
                raise ManifestError("app and runtime ids must be distinct")
            app_names.add(name)
            self._app_factories.append((spec, load_entry_point(spec["entry_point"])))
        if self._signal_transports and (self.signals.entity == 'local' or self.signals.node_id == 'local'):
            raise ManifestError('network signals require explicit entity and unique node identity')
        if self.remote:
            if self.signals.node_id in self.remote.peers:
                raise ManifestError('execution peers must exclude this node')
            for service in self.remote.expose:
                self.registry.get(service)
        for name, flow in doc.get("flows", {}).items():
            nodes = flow.get("nodes", {})
            if flow.get("start") not in nodes:
                raise ManifestError("invalid flow start: " + name)
            for node in nodes.values():
                for edge in ("next", "on_error"):
                    if node.get(edge) and node[edge] not in nodes:
                        raise ManifestError("unknown flow node")
                if node.get('routes') is not None:
                    self.signals._check_routes(node['routes'])
                if 'timeout_s' in node and (isinstance(node['timeout_s'], bool) or not isinstance(node['timeout_s'], (int, float)) or node['timeout_s'] <= 0):
                    raise ManifestError('invalid workflow timeout')
                if "operation" in node:
                    target = node.get('node', self.signals.node_id)
                    if target != self.signals.node_id:
                        if self.remote is None or target not in self.remote.peers:
                            raise ManifestError('undeclared remote workflow node: ' + target)
                        continue
                    d = self.registry.get(node["service"])
                    op = d.manifest.operation(node["operation"])
                    validate_values(op.get("arguments", {}), node.get("arguments", {}), name)
                    if op.get("control"):
                        raise ManifestError("workflow cannot invoke node control")

    # Replace nested resource references with the hardware objects created for this node.
    def _resolve(self, value):
        if isinstance(value, dict):
            if "$resource" in value:
                return self.resources[value["$resource"]]
            return {k: self._resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve(v) for v in value]
        return value

    # Construct declared hardware through injected factories or the built-in I2C implementation.
    def _create_resources(self):
        for name, spec in self.document.get("resources", {}).items():
            factory = self.resource_factories.get(spec["type"])
            if factory:
                self.resources[name] = factory(spec)
            elif spec["type"] == "i2c":
                from machine import I2C, Pin
                self.resources[name] = I2C(spec["bus"], sda=Pin(spec["sda"]),
                                           scl=Pin(spec["scl"]), freq=spec.get("frequency", 400000))
            else:
                raise ManifestError("unknown resource type: " + spec["type"])

    # Resolve hardware references in service settings before dependency-ordered initialization.
    async def prepare(self):
        for d in self.registry.definitions():
            d.config = self._resolve(d.raw_config)
        return await super().prepare()

    # Create hardware, start services and listeners, then start applications and configured
    # execution work.
    async def boot(self):
        try:
            self._create_resources()
            await self.start()
            for spec, factory in self._runtime_factories:
                instance = factory(self, **spec.get("config", {}))
                self.runtime_instances[spec["id"]] = instance
                self._runtime_instances.append(instance)
                await call(instance.start)
                task_id = self.tasks.spawn("runtime:" + spec["id"], instance.run,
                                           kind="runtime", owner=spec["id"])
                self._runtime_tasks.append(task_id)
            for name, transport in self._signal_transports:
                self._started_transports.append(transport)
                await call(transport.start)
                for direction, operation in (('rx', self.signals.listen), ('tx', self.signals.transmit)):
                    self._runtime_tasks.append(self.tasks.spawn('signals:' + name + ':' + direction,
                        operation, name, kind='runtime', owner=name))
            for spec, factory in self._app_factories:
                instance = factory(self, **spec.get("config", {}))
                self.apps[spec["id"]] = instance
                self._app_instances.append(instance)
                await call(instance.start)
                task_id = self.tasks.spawn("app:" + spec["id"], instance.run,
                    kind="app", owner=spec["id"])
                self._runtime_tasks.append(task_id)
                if spec.get("mode") == "oneshot":
                    self._oneshot_tasks.add(task_id)
            if self.remote:
                self.remote.start()
                self._runtime_tasks.append(self.tasks.spawn('execution:remote', self.remote.run, kind='runtime'))
            for name, flow in self.document.get("flows", {}).items():
                if flow.get("autostart", False):
                    self.start_flow(name)
            self._runtime_tasks.append(self.tasks.spawn("runtime:health", self._health, kind="runtime"))
            return self
        except BaseException:
            await self.shutdown()
            raise

    # Watch resident tasks and fail the node if an essential task exits unexpectedly.
    async def _health(self):
        handled = set()
        while True:
            watched = list(self._service_tasks.values()) + self._runtime_tasks
            failed = [task_id for task_id in watched if task_id not in handled
                      and task_id in self.tasks.records
                      and self.tasks.records[task_id]["state"] in ("failed", "succeeded", "cancelled")
                      and not (task_id in self._oneshot_tasks
                               and self.tasks.records[task_id]["state"] == "succeeded")]
            if failed:
                handled.update(failed)
                try:
                    await self.stop()
                finally:
                    self.state = "failed"
            await asyncio.sleep(0.05)

    # Start a named workflow only while the node accepts new operations.
    def start_flow(self, name):
        if not self.accepting:
            raise BusyError("node is " + self.state)
        return self.engine.start(name, self.document["flows"][name])

    # Require healthy runtime listeners before rebuilding the node's services.
    async def reset(self):
        for task_id in self._runtime_tasks:
            record = self.tasks.records.get(task_id)
            if record is not None and record['done'].is_set() and not (
                    task_id in self._oneshot_tasks and record['state'] == 'succeeded'):
                raise LifecycleError('runtime listener stopped; restart the node before resetting services')
        return await super().reset()

    # Invalidate remote handshakes whenever local lifecycle control changes service
    # availability.
    def _invalidate_execution(self):
        if self.remote:
            self.remote.invalidate()

    # Publish an application signal while protecting the internal execution namespace.
    def publish_signal(self, name, payload=None, **options):
        if not isinstance(name, str) or name.startswith('_rp.'):
            raise ValueError('reserved or invalid signal name')
        return self.signals.publish(name, payload, **options)

    # Combine local runs, signal statistics, and remote execution observations.
    def execution_status(self):
        return {'entity': self.signals.entity, 'node': self.signals.node_id,
                'runs': self.engine.snapshot(), 'signals': dict(self.signals.stats),
                'observed_runs': list(self.remote.states.values()) if self.remote else [],
                'remote_actions': self.remote.snapshot() if self.remote else []}

    async def wait(self):
        """Wait for a task-only node to finish, or a resident node to close."""
        specs = self.document.get("apps", [])
        if specs and all(spec.get("mode") == "oneshot" for spec in specs):
            await asyncio.gather(*(self.tasks.wait(task_id) for task_id in self._oneshot_tasks))
        else:
            await self._closed.wait()

    # Stop services and managed work, then unwind applications, transports, runtime components,
    # and resources.
    async def shutdown(self):
        self._closing = True
        errors = []
        try:
            await self.stop()
        except Exception as error:
            errors.append(str(error))
        await self.tasks.cancel_kinds(("command",))
        for task_id in reversed(self._runtime_tasks):
            if task_id in self.tasks.records:
                await self.tasks.cancel(task_id)
        self._runtime_tasks = []
        for instance in reversed(self._app_instances):
            try:
                await call(instance.stop)
            except Exception as error:
                errors.append(str(error))
        self._app_instances = []
        for transport in reversed(self._started_transports):
            try:
                await call(transport.stop)
            except Exception as error:
                errors.append(str(error))
        self._started_transports = []
        self.signals.clear_pending()
        for instance in reversed(self._runtime_instances):
            try:
                await call(instance.stop)
            except Exception as error:
                errors.append(str(error))
        self._runtime_instances = []
        self.apps.clear()
        self.runtime_instances.clear()
        for resource in self.resources.values():
            deinit = getattr(resource, "deinit", None)
            if deinit:
                try:
                    deinit()
                except Exception as error:
                    errors.append(str(error))
        self.resources = {}
        self._closed.set()
        if errors:
            raise RuntimeError("; ".join(errors))

    # Expose public service operations and control routes without deployment configuration or
    # credentials.
    def discovery(self):
        # Public service projection: never expose deployment credentials/config.
        services = {}
        for d in self.registry.definitions():
            service = dict(d.manifest.service)
            operations = {}
            for name, op in d.manifest.operations.items():
                if op.get("implementations") and d.implementation not in op["implementations"]:
                    continue
                item = dict(op)
                item["rest"] = {"method": "POST", "path": "/api/services/{}/{}".format(d.service_id, name)}
                operations[name] = item
            service["operations"] = operations
            services[d.service_id] = service
        return {"manifest": "rp.node/v1", "name": self.document.get("name", "node"),
                "identity": {"entity": self.signals.entity, "node": self.signals.node_id},
                "apps": [{"id": spec["id"], "entry_point": spec["entry_point"]} for spec in self.document.get("apps", [])],
                "signal_routes": list(self.signals.routes), "services": services, "flows": list(self.document.get("flows", {})),
                "control": {"stop": "/api/node/stop", "reset": "/api/node/reset",
                            "calibrate": "/api/node/calibrate",
                            "tasks": "/api/tasks", "status": "/api/node/status"}}


# Boot and supervise one manifest-defined node, ensuring shutdown on every exit path.
async def serve_manifest(path):
    node = NodeRuntime.load(path)
    try:
        await node.boot()
        await node.wait()
    finally:
        await node.shutdown()


# Start the event loop for a single manifest-defined node.
def run_manifest(path):
    asyncio.run(serve_manifest(path))
