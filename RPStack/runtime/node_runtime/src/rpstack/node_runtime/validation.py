"""Small shared validator used before hardware construction or dispatch."""
from .manifest import ManifestError


# Apply schema defaults and validate supplied types and constraints, rejecting undeclared
# values.
def validate_values(schema, values, label):
    unknown = [key for key in values if key not in schema]
    if unknown:
        raise ManifestError("{}: undeclared fields {}".format(label, unknown))
    result = {}
    for key, spec in schema.items():
        if key in values:
            value = values[key]
        elif "default" in spec:
            value = spec["default"]
        elif spec.get("required"):
            raise ManifestError("{}: {} is required".format(label, key))
        else:
            continue
        kind = spec.get("type")
        valid = True
        if kind == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif kind == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            if valid:
                valid = value == value and value not in (float("inf"), -float("inf"))
        elif kind == "boolean":
            valid = isinstance(value, bool)
        elif kind == "string":
            valid = isinstance(value, str)
        elif kind == "object":
            valid = isinstance(value, dict)
        if not valid:
            raise ManifestError("{}: invalid {}".format(label, key))
        if "minimum" in spec and value < spec["minimum"]:
            raise ManifestError("{}: {} below minimum".format(label, key))
        if "maximum" in spec and value > spec["maximum"]:
            raise ManifestError("{}: {} above maximum".format(label, key))
        if "enum" in spec and value not in spec["enum"]:
            raise ManifestError("{}: invalid {}".format(label, key))
        result[key] = value
    return result
