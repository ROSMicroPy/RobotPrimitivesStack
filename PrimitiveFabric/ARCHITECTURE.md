# RPStack architecture

RPStack assembles logical nodes from independently installed packages. Hardware drivers implement device access, services expose capabilities, adapters transform measurements, composites coordinate providers, and applications orchestrate robot behavior.

## Repository groups

| Group | Packages and responsibility |
|---|---|
| `foundation` | `interfaces` defines capability contracts and measurement types; `support` provides lightweight asyncio, JSON, invocation, and clock helpers. |
| `runtime` | `node_runtime` constructs and supervises nodes; `execution_engine` manages operations and workflows; `signals` handles envelopes and subscriptions; `catalog` provides discovery and composition models. |
| `transports` | `espnow` and `ros_signals` carry signal envelopes. |
| `control` | `http` and `shell` expose node controls. |
| `platform` | `bootmgr` and `env` provide startup and configuration storage. |
| `observability` | `opentelemetry` provides tracing, metrics, and logs. |
| `services` | Distance and motor providers, a distance-to-position adapter, and the linear-slide composite. |
| `apps` | `robot_gateway` exposes robot discovery over HTTP; `slide_commands` provides slide command and client applications. |
| `spec` | Node and service manifest schemas. |
| `examples` (repository root) | Device deployments and host simulations. |

Each package has one source tree under `src/rpstack`, a MIP source map, documentation, and relevant host tests. Service implementations live in `service.py`; package initializers expose their public classes. Drivers remain inside their owning service package.

## Dependency boundaries

Foundation packages import no runtime, service, or application packages. Services use contracts and portable support directly. Composites consume capability interfaces. The node runtime constructs providers and binds consumers to them. Applications submit operations through nodes. Transports carry signals; control interfaces expose node actions.

A slide client can install `rpstack.apps.slide_commands` without installing the slide hardware service. The slide service itself has no dependency on its orchestration applications.

## Vocabulary

| Term | Meaning |
|---|---|
| Device | Physical board or host environment. |
| Node | Logical runtime identity; `NodeHost` can host several nodes on one device. |
| Service type | Reusable implementation and contract definition in a manifest's `components` map. |
| Service instance | Configured capability provider constructed on a node. |
| Driver | Hardware-specific backend owned by a service. |
| Capability | Versioned service interface and provider constraints. |
| Operation | Declared callable exposed by a service. |
| App | Orchestration code with a resident or one-shot lifecycle. |
| Workflow | Declarative operation/signal graph in `flows`; its `nodes` entries are workflow steps. |
| Task | Managed execution instance tracked by `TaskRegistry`. |
| Signal | Event envelope carried by `SignalBus`. |
| Deployment | Node manifests, resources, apps, and installed packages for a scenario. |

`ServiceRegistry` resolves service dependencies. `Catalog` describes discovered nodes. `PhysicalComponent` and `CompositionRegistry` model physical assemblies and mount claims.

## Lifecycle

Providers start before consumers and stop in reverse dependency order. Service stop/reset keeps control facilities reachable. Full shutdown releases applications, transports, and runtime resources as well. Work runs through managed tasks on the node's cooperative event loop, with dedicated pulse workers for blocking motor batches.

## Installation and validation

Use package manifests at their canonical locations. Remote `package.json` files declare dependencies; `package.local.json` files describe local source maps. Example manifests list the full local installation set.

Run `python3 tools/check_architecture.py` to validate package maps and isolated installations. Run `python3 tools/run_tests.py` for host regression suites. Device memory, physical motor timing, sensor feedback, and radio behavior require hardware validation.
