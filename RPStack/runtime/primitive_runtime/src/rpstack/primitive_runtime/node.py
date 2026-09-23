"""Load one node manifest; assemble and supervise all declared services."""
from rpstack.execution_engine import ExecutionEngine, asyncio, call
from .manifest import ManifestError, ServiceManifest, load_document, load_entry_point
from .supervisor import ServiceSupervisor, BusyError
from .validation import validate_values


class NodeRuntime(ServiceSupervisor):
    def __init__(self, document, resource_factories=None):
        super().__init__()
        self.document = document
        self.resources = {}
        self.resource_factories = resource_factories or {}
        self.engine = ExecutionEngine(self.tasks, self.invoke)
        self._runtime_instances = []
        self._runtime_tasks = []
        self._closed = asyncio.Event()
        self._validate_and_register()

    @classmethod
    def load(cls, path, **kwargs):
        return cls(load_document(path), **kwargs)

    def _validate_and_register(self):
        doc = self.document
        if doc.get("manifest") != "rp.node/v1":
            raise ManifestError("expected rp.node/v1")
        if not doc.get("services") or not isinstance(doc["services"], dict):
            raise ManifestError("node requires services")
        catalog = doc.get("components", {})
        resources = doc.get("resources", {})
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
            def build_factory(factory=factory, driver=driver, constructor=constructor):
                def build(**dependencies):
                    args = self._resolve(constructor)
                    args.update(dependencies)
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
        for name, flow in doc.get("flows", {}).items():
            nodes = flow.get("nodes", {})
            if flow.get("start") not in nodes:
                raise ManifestError("invalid flow start: " + name)
            for node in nodes.values():
                for edge in ("next", "on_error"):
                    if node.get(edge) and node[edge] not in nodes:
                        raise ManifestError("unknown flow node")
                if "operation" in node:
                    d = self.registry.get(node["service"])
                    op = d.manifest.operation(node["operation"])
                    validate_values(op.get("arguments", {}), node.get("arguments", {}), name)
                    if op.get("control"):
                        raise ManifestError("workflow cannot invoke node control")

    def _resolve(self, value):
        if isinstance(value, dict):
            if "$resource" in value:
                return self.resources[value["$resource"]]
            return {k: self._resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve(v) for v in value]
        return value

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

    async def prepare(self):
        for d in self.registry.definitions():
            d.config = self._resolve(d.raw_config)
        return await super().prepare()

    async def boot(self):
        try:
            self._create_resources()
            await self.start()
            for spec, factory in self._runtime_factories:
                instance = factory(self, **spec.get("config", {}))
                self._runtime_instances.append(instance)
                await call(instance.start)
                task_id = self.tasks.spawn("runtime:" + spec["id"], instance.run,
                                           kind="runtime", owner=spec["id"])
                self._runtime_tasks.append(task_id)
            for name, flow in self.document.get("flows", {}).items():
                if flow.get("autostart", False):
                    self.start_flow(name)
            self._runtime_tasks.append(self.tasks.spawn("runtime:health", self._health, kind="runtime"))
            return self
        except BaseException:
            await self.shutdown()
            raise

    async def _health(self):
        handled = set()
        while True:
            watched = list(self._service_tasks.values()) + self._runtime_tasks
            failed = [task_id for task_id in watched if task_id not in handled
                      and task_id in self.tasks.records
                      and self.tasks.records[task_id]["state"] in ("failed", "succeeded")]
            if failed:
                handled.update(failed)
                try:
                    await self.stop()
                finally:
                    self.state = "failed"
            await asyncio.sleep(0.05)

    def start_flow(self, name):
        if not self.accepting:
            raise BusyError("node is " + self.state)
        return self.engine.start(name, self.document["flows"][name])

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
        for instance in reversed(self._runtime_instances):
            try:
                await call(instance.stop)
            except Exception as error:
                errors.append(str(error))
        self._runtime_instances = []
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
                "services": services, "flows": list(self.document.get("flows", {})),
                "control": {"stop": "/api/node/stop", "reset": "/api/node/reset",
                            "tasks": "/api/tasks", "status": "/api/node/status"}}


async def serve_manifest(path):
    node = NodeRuntime.load(path)
    try:
        await node.boot()
        await node._closed.wait()
    finally:
        await node.shutdown()


def run_manifest(path):
    asyncio.run(serve_manifest(path))
