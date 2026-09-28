# Actors and Behaviors

An Actor binds a node-local identity, configuration, lifecycle mode, and optional Behavior version to one implementation. `FabricNode.actors` contains the running Actor objects. Reusable Behavior packages live in `SomaticMesh/behaviors/`; complete deployments live in `examples/`.

## Implement a Behavior

```python
from somatic_mesh.support import Behavior

class AnnounceBehavior(Behavior):
    async def run(self):
        self.node.publish_signal('participant.ready', {'actor': self.actor.id})
        return 'ready'
```

`Behavior.__init__(actor)` exposes `self.actor` and `self.node`. Subclasses with configuration accept `(actor, **config)` and call `super().__init__(actor)`. Implement `start()` to prepare resources, `run()` for cooperative work, and `stop()` for cleanup. The base class supplies no-op preparation and cleanup hooks.

## Assign it to an Actor

Node manifest fragment:

```json
{
  "actors": [{
    "id": "announcer",
    "behavior": "my_behaviors:AnnounceBehavior",
    "version": "1.0.0",
    "mode": "oneshot",
    "config": {}
  }]
}
```

`behavior` is a Python entry point. `version` is optional deployment metadata; the runtime does not resolve or install that version. `config` is passed to the factory and excluded from public discovery. `requires` names runtime components or earlier Actors on this node. IDs must be nonempty, unique, and distinct from runtime component IDs.

`resident` is the default mode. Unexpected resident completion or any uncaught execution failure triggers node health handling. `oneshot` Actors may complete normally. A node containing only oneshot Actors finishes `wait()` when all of them finish, propagating failures.

```python
actor = node.actors['announcer']
result = await actor.wait()
print(actor.id, actor.address, actor.task_id, actor.state)
print(actor.describe())
```

The Actor owns its Behavior instance and execution task. `actor.behavior` exposes implementation-specific data, while `describe()` exposes only identity, assignment, lifecycle mode, state, and task ID. Task outcomes and errors are available through the node's task registry.

## Lifecycle and resource ownership

The node starts capability services and runtime facilities before Actors. Each Actor constructs its Behavior, calls `start()`, and schedules `run()` as a managed Actor task. Shutdown cancels execution and stops Behaviors in reverse startup order. Partial startup failure unwinds already constructed Behaviors, including the one whose preparation failed.

The host owns the event loop, shared transports, and service lifecycle. Behaviors release only their own subscriptions and resources. Use managed service operations for hardware work so resource claims and cancellation remain effective. Node `stop()` gates service operations and stops managed motion/workflows while runtime controls and resident Actor infrastructure remain available; `shutdown()` closes the whole node.

## Assign a workflow

```json
{
  "actors": [{
    "id": "sequence",
    "behavior": "somatic_mesh.execution_engine:WorkflowBehavior",
    "mode": "oneshot",
    "config": {"flow": "announce"}
  }],
  "flows": {
    "announce": {
      "start": "ready",
      "nodes": {"ready": {"emit": "sequence.ready"}}
    }
  }
}
```

An Actor-owned workflow must not also declare `autostart: true`. The Behavior waits for the flow's result and cancels its flow when Actor execution is cancelled. Direct `node.start_flow(name)` remains available for explicitly requested runs. Distributed workflow steps specify peer nodes and execute through the remote-action protocol.

Placement is fixed by deployment. Signals address nodes, not automatically relocated Actor identities. Checkpoint/restore, dynamic placement, and recovery require the additional [Fabric management design](fabric-management.html).
