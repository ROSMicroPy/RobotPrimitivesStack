# RPInterfaces

Shared, hardware-independent capability and lifecycle contracts for Robot
Primitive services. The implementation is intentionally lightweight and has no
CPython-only dependencies, so the same contracts can be used by MicroPython
drivers, host simulations, composites, and bridges.

Capability methods use canonical SI units. Existing service packages may retain
native-unit convenience methods at their compatibility boundary.
