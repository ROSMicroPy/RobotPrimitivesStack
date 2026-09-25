"""Capability matching and dependency ordering."""

from .manifest import ServiceManifest


class ResolutionError(RuntimeError):
    pass


class ServiceDefinition:
    # Combine a service manifest, configuration, bindings, and factory before an instance
    # exists.
    def __init__(self, service_id, manifest, factory=None, config=None,
                 bindings=None, implementation=None):
        if not isinstance(manifest, ServiceManifest):
            manifest = ServiceManifest(manifest)
        self.service_id = service_id
        self.manifest = manifest
        self.factory = factory
        self.config = config or {}
        self.bindings = bindings or {}
        self.implementation = implementation
        self.provides = self.manifest.provides_for(implementation)
        self.dependencies = {}
        self.instance = None


class ServiceRegistry:
    # Prepare ordered registration and lookup of service definitions.
    def __init__(self):
        self._definitions = {}
        self._order = []

    # Register a uniquely named definition while retaining declaration order.
    def register(self, definition):
        if definition.service_id in self._definitions:
            raise ResolutionError(
                "service {} is already registered".format(definition.service_id)
            )
        self._definitions[definition.service_id] = definition
        self._order.append(definition.service_id)

    # Look up a service definition or report an unknown dependency.
    def get(self, service_id):
        try:
            return self._definitions[service_id]
        except KeyError:
            raise ResolutionError("unknown service {}".format(service_id))

    # Return service definitions in their original registration order.
    def definitions(self):
        return [self._definitions[name] for name in self._order]

    # Bind dependency roles to compatible providers and derive a valid startup order.
    def resolve(self):
        for consumer in self.definitions():
            consumer.dependencies = {}
            for role, requirement in consumer.manifest.requires.items():
                target = consumer.bindings.get(role)
                if target is not None:
                    provider = self.get(target)
                    if not _definition_provides(provider, requirement):
                        raise ResolutionError(
                            "{} binding {}={} is incompatible".format(
                                consumer.service_id, role, target
                            )
                        )
                else:
                    candidates = [
                        provider for provider in self.definitions()
                        if provider.service_id != consumer.service_id
                        and _definition_provides(provider, requirement)
                    ]
                    if not candidates:
                        raise ResolutionError(
                            "{} has no provider for role {} ({})".format(
                                consumer.service_id, role, requirement["interface"]
                            )
                        )
                    if len(candidates) > 1:
                        raise ResolutionError(
                            "{} role {} is ambiguous: {}".format(
                                consumer.service_id,
                                role,
                                ", ".join(item.service_id for item in candidates),
                            )
                        )
                    provider = candidates[0]
                consumer.dependencies[role] = provider.service_id
        return self.start_order()

    # Topologically order services so providers start before their consumers.
    def start_order(self):
        temporary = {}
        permanent = {}
        ordered = []

        # Walk dependencies, detecting cycles before adding each service to startup order.
        def visit(service_id, chain):
            if service_id in permanent:
                return
            if service_id in temporary:
                raise ResolutionError(
                    "capability dependency cycle: {}".format(
                        " -> ".join(chain + [service_id])
                    )
                )
            temporary[service_id] = True
            definition = self.get(service_id)
            for dependency_id in definition.dependencies.values():
                visit(dependency_id, chain + [service_id])
            temporary.pop(service_id, None)
            permanent[service_id] = True
            ordered.append(service_id)

        for service_id in self._order:
            visit(service_id, [])
        return ordered


# Check whether any capability offered by a service satisfies a requirement.
def _definition_provides(definition, requirement):
    for capability in definition.provides:
        if _capability_matches(capability, requirement):
            return True
    return False


# Match interface, version, and every declared capability constraint.
def _capability_matches(provided, required):
    if provided.get("interface") != required.get("interface"):
        return False
    if provided.get("version") != required.get("version"):
        return False
    constraints = required.get("constraints", {})
    for key, value in constraints.items():
        if provided.get(key) != value:
            return False
    return True
