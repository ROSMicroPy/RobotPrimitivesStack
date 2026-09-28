# Robot gateway behavior

Install `package.json`
(or `package.local.json` with the workspace loader), then declare a
`somatic_mesh.micropyserver:FabricRestApi` runtime named `http`, a
`somatic_mesh.catalog:Catalog` runtime named `catalog`, and the behavior shown in
[Actors](../README.md). Multiple nodes can host gateways for the same robot.

The behavior mounts on the existing HTTP server. It creates no server socket, radio,
thread or independent mesh listener. Its stop method removes only its own routes.

| GET endpoint | Result |
| --- | --- |
| `/api/robot` | Entity, gateway identity, live nodes, actors, service capabilities and composition |
| `/api/robot/status` | Node state, signal counters, catalog counters and known-node count |
| `/api/robot/messages` | Bounded, non-destructive recent remote signals |
| `/health` | Behavior health/version |

Responses use the `somatic.catalog/v1` projection.
The standard `/manifest`, task, execution and service routes remain on the same
listener. Signal logs exclude catalog fragments and local-origin signals.

Open TheLoom's **System** view and enter a gateway URL. The VS Code
extension host queries the API, avoiding browser CORS and mixed-content issues.
Remote VS Code sessions must have network access to the gateway from their host.
The view shows node/service/behavior composition, capabilities, signal counters and
recent messages; it polls every three seconds and marks failed refreshes visibly.

See [gateway-only deployment](../../../examples/mesh_gateway/README.md) and
[linear-slide deployment](../../../examples/linear_slide/README.md).
