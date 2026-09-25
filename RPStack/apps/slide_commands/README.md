# Slide command applications

`SlideCommandApp` listens for addressed slide commands, submits operations to a node, and returns correlated completion or failure signals. `MoveOnceApp` is a client application that completes after its requested motion.

These applications orchestrate an existing node and service; they do not implement motor control or position feedback. A client can install this package without installing the linear-slide hardware service. Import them from `rpstack.apps.slide_commands`.

See the [slide-node deployment](../../../examples/slide_nodes/README.md) for device manifests and host simulation.
