# Fabric management roadmap

**Design specification.** The runtime supports fixed Actor placement, lifecycle supervision, workflows, discovery, and leased remote operations. Automatic placement, cross-host Actor ownership, controlled activation, and stateful recovery require the management work described here.

## Application, hardware, and deployment

Separate three descriptions as management evolves:

| Description | Contents |
| --- | --- |
| Application | Actors, Behaviors, connections, capability requirements, and recovery policy |
| Device profile | Hardware identity, pins, peripherals, firmware, and resource budgets |
| Deployment plan | Placement, bindings, exact code revisions, and eligible fallback hosts |

The `somatic.node/v1` runtime manifest contains concrete host assignments. A management compiler should produce those manifests from higher-level descriptions. Actor addresses include their host node; location-independent addressing needs an explicit routing and ownership design.

## Discovery, readiness, and authority

Discovery reports observed participants. Inventory should report installed code and configuration. Readiness should establish successful preparation. Renewable run permission should gate activation. An ownership protocol must determine which Actor instance is authorized to act on a resource.

A missing catalog announcement is not evidence that a device stopped. Remote-action leases bound requested work; they do not authorize Actor takeover. Recovery needs instance generations or equivalent fencing enforced at resource boundaries. Leave work inactive if an old instance cannot be fenced.

Start with one designated onboard coordinator. Coordinator failover is a separate milestone. Local operation and already permitted recovery should survive The Loom disconnecting. See [bootstrap](bootstrap.html) for the design of preparation and activation.

## Delivery and recovery

The Loom should resolve exact package versions and deliver verified installations. Preinstall Behavior code on eligible fallback hosts so recovery does not require internet access or desktop availability. Devices should report inventory and enforce compatibility. Peer-to-peer package distribution is not a prerequisite.

| Recovery mode | Requirements |
| --- | --- |
| Stateless restart | Eligible resources, available code, fresh ownership, and explicit handling of interrupted effects |
| Planned stateful handoff | Quiesce work, checkpoint compatible state, transfer ownership, restore, activate |
| Crash recovery | Previously persisted or replicated state; state held only on a failed device is unavailable |
| Resource-aware placement | Resource measurements and policy plus all ownership and recovery prerequisites |

Transparent migration of arbitrary Python execution and exactly-once physical effects are outside this design. Moving CPU work cannot reconnect a motor attached exclusively to a failed board or remove its local power load.

## Milestones

1. Define application and device descriptions that compile to fixed deployments.
2. Add location-independent Actor addressing and authoritative instance ownership.
3. Implement inventory, preparation, and controlled activation.
4. Enable stateless restart on preprovisioned eligible hosts.
5. Add selected checkpoint/restore and planned handoff.
6. Add resource-aware placement using measured memory, compute, power, thermal, and communication costs.

Preserve capability contracts, hardware ownership, managed operations, resource claims, and observability throughout. [Software registry design](registries.html) covers component metadata and deployment locks.
