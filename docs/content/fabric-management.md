# Fabric management and recovery

**Design proposal.** This page describes Somatic Mesh's intended management responsibilities and implementation sequence. Stable Actor addressing, automatic placement, Actor ownership, restart on alternative hosts, and stateful handoff are not current runtime guarantees.

## From node assembly to Actor deployment

Today, an application assembles services, apps, and flows on predefined logical nodes. The proposed model defines Actors and their Behaviors independently of placement, then deploys them onto eligible Fabric Nodes. Eligibility depends on required capabilities, compatible code and firmware, available resources, physical access, and application policy.

The initial implementation should keep placement explicit. Stable Actor identity and addressing must be established before automatic relocation. The current node/service addresses and task IDs remain the supported interfaces until that layer exists.

## Desired state and observed state

Fabric management should reconcile an application definition, device profiles, and an exact deployment plan with reported inventory and health. Keep these decisions distinct:

1. **Discovery:** which participants have been observed?
2. **Inventory:** which code, configuration, and hardware are installed?
3. **Readiness:** have required preparation and binding checks succeeded?
4. **Run permission:** is this instance authorized to operate now?
5. **Ownership:** which current Actor instance may act on the assigned resources?

The catalog answers discovery questions. A missing announcement is not proof that a device stopped, and a discovery timeout must not authorize takeover. Existing remote-action leases and correlation support bounded distributed operations; they do not establish exclusive Actor ownership across failures.

## Authority and hardware ownership

An Actor identity must have an authoritative current owner. Recovery must prevent an old and a replacement instance from simultaneously controlling machinery, including after a network partition or delayed message. The design needs instance generations or equivalent fencing enforced at the resource access boundary, plus expiring permission and explicit transfer rules. The exact protocol remains to be designed and validated.

Local resource claims remain useful but do not replace cross-host authority. If an old instance cannot be fenced from a physical resource, activating a replacement is not a safe recovery strategy. Reconciliation must be able to leave an Actor inactive and report why.

Start with one designated onboard coordinator. Its absence should prevent new activation and follow the deployment's permission-expiry policy. Coordinator failover is a separate milestone, not a consequence of Actor restart support. See [bootstrap](bootstrap.html) for the proposed preparation and run-permission lifecycle.

## Code delivery and offline operation

The Loom should resolve dependencies and deliver exact packages and deployment records. Preinstall the required Behavior code on eligible fallback hosts so permitted recovery can work without the desktop or internet. Devices report inventory and enforce compatibility; they do not initially need peer-to-peer package distribution or their own registry resolver.

The Loom observes and changes desired state through management interfaces. ILA should use those same interfaces. Neither should be required to remain connected for a deployed system to operate or perform already permitted recovery. [Registries](registries.html) describes the proposed software discovery and locking model.

## Recovery modes

| Mode | Required conditions | Limits |
| --- | --- | --- |
| Fixed placement | Explicit host and capability bindings | Initial Actor milestone; no relocation |
| Stateless restart elsewhere | Eligible host, installed code, fresh authorization, and safe handling of interrupted work | Restarting computation does not undo or prove completion of external effects |
| Planned stateful handoff | Quiesce work, checkpoint compatible state, transfer ownership, restore, then activate | Selected Behaviors must define checkpoint/restore and in-flight message handling |
| Crash recovery | Previously persisted or replicated state and a valid ownership decision | State held only on a dead device is lost; recovery may resume from an older checkpoint |
| Resource-aware placement | Measured resource conditions and policy, plus all migration prerequisites | CPU, memory, power, temperature, and communication costs constrain placement |

There is no promise of transparent migration of arbitrary Python execution, exactly-once physical actions, or recovery of a peripheral wired exclusively to a dead controller. Behaviors with external effects need explicit retry, deduplication, or reconciliation rules before restart is enabled.

## Development sequence

1. Define Actor identity, Behavior versions, configuration, state, and lifecycle; retain the distinction from tasks and services.
2. Separate application definitions, hardware profiles, and concrete deployment plans.
3. Add stable Actor addressing with fixed placement and explicit capability bindings.
4. Introduce inventory, preparation, authoritative ownership, and controlled activation with an onboard coordinator.
5. Support stateless restart on preprovisioned eligible hosts, including stale-instance fencing and interrupted-operation handling.
6. Add checkpoint/restore and planned handoff for selected stateful Behaviors, followed by resource-aware placement.

Keep capability contracts, transport independence, hardware ownership, managed operations, resource claims, and observability throughout. The current package layers remain foundations for this work; this proposal does not create new packages or supported manifest fields.
