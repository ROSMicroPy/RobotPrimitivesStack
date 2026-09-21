# Robot Primitive Service Manifest v1

`component.yaml` is now the canonical Robot Primitive service manifest. It is
not only WebTester metadata: it is the generic, transport-independent contract
used by the runtime, tooling, bridges, and future WebTester implementation.

Every manifest uses `manifest: rp.service/v1` and describes:

- service identity, kind, version, and entry point;
- provided and required capability interfaces;
- lifecycle method mappings;
- instance configuration;
- concrete implementation choices;
- callable operations, their arguments, results, concurrency, and safe state;
- emitted and consumed signals;
- declarative automatic, manual, or hardware tests.

The runtime treats only declared operations as remotely invokable. This makes
the manifest an allowlist as well as enough information for a UI or CLI to
build an operation form.

## Capability binding

Requirements are keyed by constructor role. A composite declaring `motor` and
`position` receives those service instances as keyword arguments. Automatic
binding succeeds only when exactly one provider matches the interface version
and all constraints. A device manifest can supply explicit role bindings when
more than one compatible provider exists.

## Tests

Tests are sequences of declared operations. `automatic` tests may be run by a
health-check workflow. `manual` and `hardware` tests require explicit approval,
which prevents a generic test runner from moving a mechanism unexpectedly.

## Deployment

YAML is the human-authored form. Host tools load it directly. Constrained
MicroPython builds can deploy an equivalent JSON document because JSON loading
is available without adding a YAML parser to device firmware.

The machine-readable schema is `service-manifest.schema.json`.


## REST transport

A device exposes its active service manifest at `GET /manifest`. Operations can
optionally declare an explicit browser-callable route:

```yaml
rest:
  method: GET
  path: /api/distance/observe
```

When an operation omits `rest`, the standard route is
`POST /api/operations/<operation-name>`. REST adapters must expose only
manifest-declared operations, accept/return JSON, and provide CORS/OPTIONS
responses for browser clients. Transport metadata does not change the Python
`method` mapping used by the runtime.
