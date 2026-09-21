"""Loading and validation for Robot Primitive service manifests."""

try:
    import ujson as json
except ImportError:
    import json


SCHEMA_ID = "rp.service/v1"


class ManifestError(ValueError):
    pass


def load_document(path):
    """Load a JSON or YAML manifest.

    JSON works on stock MicroPython. YAML is the authoring format and requires
    PyYAML (or a compatible ``yaml.safe_load`` implementation) at runtime.
    """
    with open(path, "r") as handle:
        source = handle.read()
    lower = path.lower()
    if lower.endswith(".json"):
        return json.loads(source)
    if lower.endswith(".yaml") or lower.endswith(".yml"):
        try:
            import yaml
        except ImportError:
            raise ManifestError(
                "YAML loading is unavailable; deploy a generated JSON manifest"
            )
        return yaml.safe_load(source)
    raise ManifestError("manifest must use .json, .yaml, or .yml")


class ServiceManifest:
    """Validated view over the generic service-manifest dictionary."""

    def __init__(self, document, source=None):
        if not isinstance(document, dict):
            raise ManifestError("manifest root must be a mapping")
        self.document = document
        self.source = source
        self._validate()

    @classmethod
    def load(cls, path):
        return cls(load_document(path), path)

    def _validate(self):
        if self.document.get("manifest") != SCHEMA_ID:
            raise ManifestError("manifest must be {}".format(SCHEMA_ID))
        service = self.document.get("service")
        if not isinstance(service, dict):
            raise ManifestError("service must be a mapping")
        for field in ("name", "version", "kind", "type"):
            if field not in service:
                raise ManifestError("service.{} is required".format(field))

        capabilities = service.get("capabilities", {})
        if not isinstance(capabilities, dict):
            raise ManifestError("service.capabilities must be a mapping")
        provides = capabilities.get("provides", [])
        requires = capabilities.get("requires", {})
        if not isinstance(provides, list):
            raise ManifestError("service.capabilities.provides must be a list")
        if not isinstance(requires, dict):
            raise ManifestError("service.capabilities.requires must be a mapping")
        for capability in provides:
            _validate_capability(capability, "provided capability")
        for role, requirement in requires.items():
            if not role or not isinstance(role, str):
                raise ManifestError("capability role names must be strings")
            _validate_capability(requirement, "required capability {}".format(role))

        lifecycle = service.get("lifecycle", {})
        if not isinstance(lifecycle, dict):
            raise ManifestError("service.lifecycle must be a mapping")
        operations = service.get("operations", {})
        if not isinstance(operations, dict):
            raise ManifestError("service.operations must be a mapping")
        for name, operation in operations.items():
            if not isinstance(operation, dict):
                raise ManifestError("operation {} must be a mapping".format(name))
            if "method" not in operation:
                raise ManifestError("operation {} requires method".format(name))
            arguments = operation.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ManifestError("operation {} arguments must be a mapping".format(name))

        implementations = service.get("implementations", {})
        if not isinstance(implementations, dict):
            raise ManifestError("service.implementations must be a mapping")
        for name, implementation in implementations.items():
            if not isinstance(implementation, dict):
                raise ManifestError("implementation {} must be a mapping".format(name))
            implementation_capabilities = implementation.get("capabilities", {})
            if not isinstance(implementation_capabilities, dict):
                raise ManifestError(
                    "implementation {} capabilities must be a mapping".format(name)
                )
            for capability in implementation_capabilities.get("provides", []):
                _validate_capability(
                    capability, "implementation {} capability".format(name)
                )

        tests = service.get("tests", {})
        if not isinstance(tests, dict):
            raise ManifestError("service.tests must be a mapping")
        for name, test in tests.items():
            if not isinstance(test, dict):
                raise ManifestError("test {} must be a mapping".format(name))
            steps = test.get("steps")
            if not isinstance(steps, list) or not steps:
                raise ManifestError("test {} requires one or more steps".format(name))
            for step in steps:
                if not isinstance(step, dict) or "operation" not in step:
                    raise ManifestError("test {} has an invalid step".format(name))
                if step["operation"] not in operations:
                    raise ManifestError(
                        "test {} references unknown operation {}".format(
                            name, step["operation"])
                    )

    @property
    def service(self):
        return self.document["service"]

    @property
    def name(self):
        return self.service["name"]

    @property
    def version(self):
        return str(self.service["version"])

    @property
    def kind(self):
        return self.service["kind"]

    @property
    def entry_point(self):
        return self.service.get("entry_point")

    @property
    def provides(self):
        return self.service.get("capabilities", {}).get("provides", [])

    @property
    def requires(self):
        return self.service.get("capabilities", {}).get("requires", {})

    @property
    def lifecycle(self):
        return self.service.get("lifecycle", {})

    @property
    def configuration(self):
        return self.service.get("configuration", {})

    @property
    def operations(self):
        return self.service.get("operations", {})

    @property
    def implementations(self):
        return self.service.get("implementations", {})

    @property
    def tests(self):
        return self.service.get("tests", {})

    def operation(self, name):
        try:
            return self.operations[name]
        except KeyError:
            raise ManifestError("operation {} is not declared".format(name))

    def test(self, name):
        try:
            return self.tests[name]
        except KeyError:
            raise ManifestError("test {} is not declared".format(name))

    def implementation(self, name):
        if name is None:
            return {}
        try:
            return self.implementations[name]
        except KeyError:
            raise ManifestError("implementation {} is not declared".format(name))

    def provides_for(self, implementation_name=None):
        provided = list(self.provides)
        provided.extend(
            self.implementation(implementation_name)
            .get("capabilities", {})
            .get("provides", [])
        )
        return provided


def _validate_capability(capability, label):
    if not isinstance(capability, dict):
        raise ManifestError("{} must be a mapping".format(label))
    if not capability.get("interface"):
        raise ManifestError("{} requires interface".format(label))
    version = capability.get("version")
    if not isinstance(version, int) or version < 1:
        raise ManifestError("{} version must be a positive integer".format(label))


def load_entry_point(specification):
    if not specification or ":" not in specification:
        raise ManifestError("entry_point must use module:attribute syntax")
    module_name, attribute_name = specification.split(":", 1)
    try:
        import importlib
        module = importlib.import_module(module_name)
    except ImportError:
        module = __import__(module_name, None, None, (attribute_name,))
    return getattr(module, attribute_name)
