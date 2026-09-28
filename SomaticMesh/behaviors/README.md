# Behaviors

Behavior implementations live in `SomaticMesh/behaviors/<package>/src/somatic_mesh/behaviors/<package>/`. A Fabric Node assigns each implementation to a named Actor through a `somatic.node/v1` manifest.

Factories receive `(actor, **config)` and expose `start()`, `run()`, and `stop()`. Subclass `somatic_mesh.support.Behavior` to obtain `self.actor` and `self.node`. Services provide capabilities; Behaviors decide when and how to use them. The node owns shared transports and service lifecycle.

See [Actors and Behaviors](../../docs/content/actors.md) for manifests, oneshot/resident modes, workflow assignments, and cleanup semantics.
