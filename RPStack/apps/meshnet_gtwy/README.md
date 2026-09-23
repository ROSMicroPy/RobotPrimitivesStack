# Meshnet gateway app

The RPStack successor to LighthouseMesh's `dnet_gtwy`. Install `package.json`
(or `package.local.json` with the workspace loader), then declare a
`rpstack.micropyserver:NodeRestApi` runtime named `http`, a
`rpstack.catalog:Catalog` runtime named `catalog`, and the app shown in
[Node apps](../README.md). Multiple nodes can host gateways for the same robot.

The app mounts on the existing HTTP server. It creates no server socket, radio,
thread or independent mesh listener. Its stop method removes only its own routes.

| GET endpoint | Result |
| --- | --- |
| `/api/robot` | Entity, gateway identity, live nodes, apps, service capabilities and composition |
| `/api/robot/status` | Node state, signal counters, catalog counters and known-node count |
| `/api/robot/messages` | Bounded, non-destructive recent remote signals |
| `/health`, `/version` | App health/version |

`/nodes`, `/status`, and `/messages` are path aliases. Responses use the new
`rp.catalog/v1` projection, not the old gateway's profile/event wire format.
The standard `/manifest`, task, execution and service routes remain on the same
listener. Signal logs exclude catalog fragments and local-origin signals.

Open RobotArchitect's **System** view and enter a gateway URL. The VS Code
extension host queries the API, avoiding browser CORS and mixed-content issues.
Remote VS Code sessions must have network access to the gateway from their host.
The view shows node/service/app composition, capabilities, signal counters and
recent messages; it polls every three seconds and marks failed refreshes visibly.

See [gateway-only deployment](../../../TestApps/mesh_gateway/README.md) and
[linear-slide deployment](../../../TestApps/linear_slide/README.md).
