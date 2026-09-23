# Entity-scoped signals and distributed execution

A robot is an entity (`Robie1`); each chip or host has a unique node identity
(`controller`, `arm`, `base`). Signals use the same envelope locally, over
ESP-NOW, and over ROS. A workflow has one coordinator that advances its graph;
its actions can execute on different nodes. Other nodes observe its revisioned
state and can send signals to advance it. Each run has a unique correlation ID.
There is no replicated consensus or automatic coordinator failover.

The runnable [Robie1 example](../../../TestApps/robie1/README.md) loads three
node manifests and exercises this model without hardware.

## Manifest configuration

```json
{
  "identity": {"entity": "Robie1", "node": "controller"},
  "signals": {
    "routes": ["local", "mesh", "ros"],
    "bridges": {"mesh": ["ros"], "ros": ["mesh"]},
    "transports": [
      {"id": "mesh", "entry_point": "rpstack.meshnet:EspNowTransport", "relay": true},
      {"id": "ros", "entry_point": "rpstack.ros_bridge:RosTransport",
       "config": {"backend": "rosmicropy", "init": {"agent_ip": "192.168.1.10", "agent_port": 8888}}}
    ]
  },
  "execution": {"peers": ["arm", "base"], "expose": [], "lease_ms": 3000}
}
```

Merge these fields into an `rp.node/v1` manifest. For CPython ROS 2 use backend
`rclpy`; for the included firmware use `rosmicropy`. Install the `signals`,
`meshnet`, and/or `ros_bridge` packages along with the execution engine and
primitive runtime. Imports of hardware/ROS libraries occur only at transport
startup. Wi-Fi runtime startup precedes signal transport startup.

`routes` selects where **locally published** signals go. Any subset of `local`,
`mesh`, and `ros` is valid, including local-only, mesh-only, ROS-only, and both
networks without local publication. Omitted routes default to `["local"]`.
Incoming network signals addressed to this node or `*` are delivered locally.
`bridges` explicitly forwards between named transports. `relay: true` also
rebroadcasts incoming signals on that transport, enabling bounded mesh flooding.
Relaying preserves source identity, boot ID, sequence and correlation.
A packet received on both networks is delivered once.

Transports implement async `start()`, `recv()` (one encoded envelope),
`send(bytes)` and `stop()`. The runtime owns their RX/TX tasks and fault handling;
`ps` lists `signals:<transport>:rx/tx` and `execution:remote`. Application stop
keeps these listeners available; node shutdown cancels them and closes adapters.
A failed listener stops the application through the existing health monitor.
A service reset is rejected while a runtime listener is dead; restart the node
to rebuild its transports.

## Service and workflow use

A service instance can declare `"inject_signals": true` in its node manifest.
The runtime passes its entity's bus as the constructor keyword `signals`.
Services can publish without knowing which transports the deployment selected:

```python
signals.publish("arm.ready", {"position": 0.25})
subscription = signals.subscribe("operator.continue", correlation=run_id)
try:
    message = await subscription.get(timeout=30)
finally:
    subscription.close()
```

Signal publication is synchronous bounded enqueueing; network I/O is performed
by the transport tasks. `publish` accepts `routes`, `target`, `correlation`,
`ttl_ms` and `hops` overrides. Subscriptions optionally filter source and run
correlation. Names beginning `_rp.` belong to the execution protocol; REST and
shell publication reject them.

A coordinator graph can use `"node": "arm"` on an operation step. Both nodes
must declare each other in `execution.peers`, and the worker must include the
service in `execution.expose`. The receiver uses the ordinary supervisor:
argument validation, operation allowlists and resource exclusion still apply.
Remote control operations are prohibited. Calls are not automatically retried;
timeout follows the graph's `on_error` path, if present. A dropped result can
mean the physical action completed even though the coordinator reports failure.

`correlated: true` on a wait matches only that run; `signal_source` optionally
restricts its sender. Uncorrelated waits intentionally respond to shared
external events. An `emit` carries the current run ID. Subscriptions are
established before actions and removed on cancellation. Terminal task history
is bounded. Signals emitted before subscriptions exist are not replayed.

`GET /api/execution` reports local runs, remote actions, observed coordinator
states and signal counters. Observed state is best-effort telemetry and can be
stale. `POST /api/flows/start` returns both task ID and run ID. Use
`POST /api/signals` (also `/api/events`) with `name`, `payload` and optional
routing/correlation fields. Shell `execution` prints the same execution status.

## Delivery and cancellation limits

The compact JSON wire envelope (`v,e,n,b,q,s,p,c,t,h,l`) includes version, entity,
source, random boot identity, sequence, signal name, JSON payload, correlation,
target, hop budget and remaining TTL. Maximum encoded size defaults to 2048
bytes. Version/field/type/size checks reject invalid envelopes and other entities.
A 64-sequence replay window per source/boot suppresses duplicates across routes;
packets further out of order are dropped. Origin windows expire after 60 seconds
of inactivity. The default origin cap is 512; this is configurable with
`seen_limit`. Queue depth defaults to 16 (`queue_limit`). Subscriber overflow
fails the waiter; publication rejects a full egress before delivering locally.
Ingress forwarding is best effort and counts congestion drops.

TTL is decremented for time spent in RPStack transport queues and checked while
waiting in subscriptions. It is not a synchronized wall-clock deadline: radio,
DDS and intermediary buffering can add time. Hops default to 8, maximum 16.
These are bounded transient messages, not a durable delivery/replay system.
Entity names and peer lists are routing/admission controls, not authentication.
The broadcast ESP-NOW adapter does not provide encrypted peer authentication.

Each remote action has a receiver-enforced lease (default 3000 ms, maximum
10000 ms), renewed by the coordinator. Cancellation sends an explicit message;
lost cancellation is bounded by lease expiry after the last delivered renewal.
Cancellation propagates into the worker's managed operation. Drivers must yield
and implement cleanup for this to work. Cooperative leases are not hardware
emergency stops or hard real-time guarantees.

A worker generation handshake fences delayed pre-reset calls. Duplicate logical
calls and cancellation tombstones are retained for 60 seconds after completion,
with a default cap of 64 (`execution.capacity`); when full, new work is rejected.
Lease and dedup state are in RAM. Reboots discard it; there is no exactly-once
execution across crashes. Reset invalidates the worker generation and cancels
local actions. Stopping a coordinator cancels the remote actions of its active
flows, but is not a broadcast stop of unrelated workflows on every robot node.

## LighthouseMesh refactor

The source analysis covered `LighthouseMesh/dnet/src/signalling`, `messaging`,
and `execution`. The new runtime implementation is in RPStack's `signals`,
`meshnet`, `ros_bridge`, and `execution_engine` packages; it does not import or
run the prototype submodule. Historical sources are retained under `RPStack/legacy/LighthouseMesh`.

Retained concepts: transient signals separate from persistent composition,
source/boot/sequence identities, and ESP-NOW fragmentation. Replaced the
singleton mesh/telemetry coupling, IRQ processing and threaded workflow execution
with manifest-owned async services. Added robot scope, targeting, correlation,
explicit bridges, replay windows, bounded reassembly, leased remote execution
and reset fencing. The old `dnet` APIs and v2 event envelope are not supported.
Persistent node/capability discovery is provided by `runtime/catalog`, with
REST access through `apps/meshnet_gtwy`. Legacy composition models are retained
in the catalog package. OTA and prototype topology tooling remain reference code.
