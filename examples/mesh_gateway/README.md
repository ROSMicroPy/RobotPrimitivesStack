# Gateway-only node

Install `package.json` with the workspace loader, or `package.github.json` with
mip. Set `WIFI_SSID` and `WIFI_PASSWORD` in the node environment. `main.py` starts
`mesh_gateway_manifest.json`, with shared Wi-Fi/HTTP, catalog and the gateway app.

Set `identity.entity` to the robot's entity and give every node a unique
`identity.node`. Enable the catalog and a mesh signal route on other robot nodes.
ESP-NOW peers must use the same channel as the gateway's Wi-Fi access point.
Multiple nodes may use this deployment with different identities.

Query `/api/robot`, or connect RobotArchitect's System view to the node's IP.
The linear-slide example also includes this gateway app; it remains local-only
until its `signals` configuration declares a network transport and route.
