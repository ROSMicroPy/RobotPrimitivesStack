"""Declarative execution of tests described by a service manifest."""


class ManifestTestError(RuntimeError):
    pass


class ManifestTestRunner:
    # Connect manifest test execution to the supervisor that owns service operations.
    def __init__(self, supervisor):
        self.supervisor = supervisor

    # Resolve test parameters, invoke declared steps, and record outcomes while respecting
    # manual-test gating.
    async def run(self, service_id, test_name, parameters=None, allow_manual=False):
        definition = self.supervisor.registry.get(service_id)
        specification = definition.manifest.test(test_name)
        mode = specification.get("mode", "manual")
        if mode != "automatic" and not allow_manual:
            raise ManifestTestError(
                "test {} is {}; explicit approval is required".format(
                    test_name, mode
                )
            )
        parameters = _resolve_parameters(specification, parameters or {})
        results = []
        for index, step in enumerate(specification["steps"]):
            try:
                result = await self.supervisor.invoke(
                    service_id,
                    step["operation"],
                    _substitute(step.get("arguments", {}), parameters),
                )
                _assert_expectation(result, step.get("expect"))
                results.append({"step": index, "passed": True, "result": result})
            except Exception as error:
                results.append({"step": index, "passed": False, "error": str(error)})
                return {"name": test_name, "passed": False, "steps": results}
        return {"name": test_name, "passed": True, "steps": results}


# Apply test parameter defaults and reject missing required or undeclared inputs.
def _resolve_parameters(specification, supplied):
    resolved = {}
    for name, parameter in specification.get("parameters", {}).items():
        if name in supplied:
            resolved[name] = supplied[name]
        elif "default" in parameter:
            resolved[name] = parameter["default"]
        elif parameter.get("required", False):
            raise ManifestTestError("test parameter {} is required".format(name))
    unknown = [name for name in supplied if name not in specification.get("parameters", {})]
    if unknown:
        raise ManifestTestError("undeclared test parameters: {}".format(", ".join(unknown)))
    return resolved


# Recursively replace parameter placeholders in a test step's argument structure.
def _substitute(value, parameters):
    if isinstance(value, dict):
        if set(value.keys()) == {"$parameter"}:
            name = value["$parameter"]
            if name not in parameters:
                raise ManifestTestError("test parameter {} is unavailable".format(name))
            return parameters[name]
        return {key: _substitute(item, parameters) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, parameters) for item in value]
    return value


# Compare a result with exact-value or selected-field expectations and explain mismatches.
def _assert_expectation(result, expectation):
    if expectation is None:
        return
    value = result.as_dict() if hasattr(result, "as_dict") else result
    if "equals" in expectation and value != expectation["equals"]:
        raise ManifestTestError(
            "expected {!r}, received {!r}".format(expectation["equals"], value)
        )
    subset = expectation.get("fields")
    if subset is not None:
        if not isinstance(value, dict):
            raise ManifestTestError("field expectation requires a mapping result")
        for key, expected in subset.items():
            if value.get(key) != expected:
                raise ManifestTestError(
                    "expected {}={!r}, received {!r}".format(
                        key, expected, value.get(key)
                    )
                )
