# LighthouseMesh migration reference

`LighthouseMesh/` preserves the tracked source, design material, demos and tests
from the former LighthouseMesh submodule. It is historical reference material,
not an installed RPStack package. No active RPStack package depends on it.

The production integration is split by responsibility:

| LighthouseMesh responsibility | RPStack home |
| --- | --- |
| ESP-NOW fragmentation and transport | `runtime/meshnet` |
| Entity-scoped messaging and routing | `runtime/signals` |
| Async/distributed execution | `runtime/execution_engine` |
| Node and capability discovery | `runtime/catalog` |
| Physical composition and capability reconciliation models | `runtime/catalog` |
| `dnet_gtwy` REST service | `apps/meshnet_gtwy` on shared `micropyserver` |
| `gtwy_webui` node/status/message visualization | RobotArchitect System view |

The prototype's standalone HTTP server, singleton/threaded mesh loop and old
wire protocol are replaced by RPStack's supervised runtime. Historical tools,
experiments and design documents remain here for reference. Existing legacy
firmware must migrate to the RPStack signal/catalog protocol to participate.
