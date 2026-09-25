# Service and app registries

**Design proposal.** This page defines the intended Robot Architect registry
model. Registry schemas, publishing automation, multi-registry discovery, and
deployment locking described here are not yet implemented. JSON examples are
proposed formats, not inputs supported by the current runtime.

## Available software and observed devices

A software registry lists services and apps available to install. The runtime
catalog lists nodes and capabilities actually observed on the robot. Architect
uses both to display desired configuration alongside installed state.

| Document | Question it answers |
| --- | --- |
| Registry index | Which services and apps are available? |
| Versioned service/app descriptor | What does this version do, require, and support? |
| Package manifest (`package.json`) | Which files and package dependencies install it? |
| Node manifest | Which configured instances and bindings should this logical node have? |
| Deployment lock | Exactly which sources, versions, files, and manifests belong on this robot? |

One package may expose several selectable services or apps. Registry entries
represent those components and reference their installation packages. Each app
needs metadata for its entry point, configuration, and required capabilities,
just as services need their component contracts.

## One descriptor per component and published version

Maintain the current descriptor alongside each component's source. Git retains
historical source versions. Publishing creates an immutable descriptor for each
released component version; authors do not maintain one growing central list.

```text
Source repository:
  RPStack/services/motor_control/
    component.yaml
    package.json
    src/...

Published registry:
  index.json
  services/motor_control/
    index.json
    0.4.0.json
    0.5.0.json
  apps/slide_commands/
    index.json
    0.1.0.json
```

The top-level index holds stable component IDs, names, summaries, kinds, and links
to version indexes. Each component index lists available versions and links to
their descriptors. Architect fetches detailed metadata as needed. Both index
levels are generated, not edited manually. Published versions cannot be replaced
with different contents; fixes require a new version.

## Dependencies and versions

Descriptors declare dependency versions, but distinguish software installation
from runtime service binding:

| Dependency | Resolution |
| --- | --- |
| Package | Install compatible code on the device |
| Service instance | Bind a configured provider for a required role |
| Capability/interface | Select a provider implementing a compatible contract and constraints |

Prefer capability requirements where providers are interchangeable. Require a
specific service implementation only when the consumer depends on it. Keep
implementation versions separate from interface versions: service `0.4.0` may
implement interface version `1`.

Illustrative version descriptor fragment; the IDs and compatibility range below
are examples, not a claim about the current linear-slide contract:

```json
{
  "schema": "rp.registry.service/v1",
  "id": "rp.linear_slide",
  "version": "0.3.0",
  "source": {
    "repository": "ROSMicroPy/RobotPrimitivesStack",
    "commit": "<full-source-commit-sha>",
    "package": "RPStack/services/linear_slide/package.json"
  },
  "dependencies": {
    "services": [
      {
        "role": "motor",
        "service": "rp.motor_control",
        "version": ">=0.4.0 <0.5.0",
        "interface": "motion.motion_actuator",
        "interface_version": 1,
        "placement": "same_device"
      }
    ]
  }
}
```

Define one version-range syntax for the registry. Architect resolves compatible
ranges into exact versions, source commits, and file hashes in the deployment
lock. Resolve the full transitive graph across all logical nodes on each device;
reject missing dependencies, incompatible versions, and lifecycle dependency
cycles before installation.

Package requirements have one authoritative declaration, currently `package.json`.
Generate their registry representation from it. Service requirements should extend
the existing capability contracts and binding model rather than create a competing
runtime dependency system. CI should reject inconsistent representations.

Selecting a service may suggest required providers, but must not silently assign
hardware pins or assume that a remote provider is supported. Validate placement,
driver compatibility, resource ownership, and explicit bindings before deployment.

## Publishing and testing branches

A proposed GitHub Action runs on relevant pushes and validates descriptors,
unique component IDs, package references, and dependency declarations. It generates
deterministically ordered indexes and publishes only validated results.

Publish registry snapshots keyed by source commit, with a pointer for each branch
to its latest successfully validated snapshot. A dedicated registry branch can
hold these generated documents without adding generated commits to every source
branch. Released version descriptors remain available when branch pointers advance.
The registry index and every referenced source file must agree on the source
snapshot. A failed publication leaves the previous valid pointer intact.

Architect supports selecting a branch, tag, or commit for Git-backed sources.
Browsing may follow a branch; deployments retain the resolved immutable commit.
Testing builds need commit-qualified identities because several commits may share
the same development version. Show the selected branch and resolved commit in
Architect so users can distinguish a moving source from an installed build.

Same-repository dependencies resolve consistently to the selected snapshot unless
explicitly overridden. Existing package references to `archdef` must be accounted
for by the resolver; selecting a testing branch must not silently mix its code
with dependency code from another branch.

## Multiple registries and private sources

Architect supports several enabled sources and presents their apps and services
in one searchable palette, with their origin visible. Each source has a stable
registry identity, display name, index URL, optional Git ref, optional credential
reference, and enabled state. Arbitrary HTTP registries need not expose Git refs.

Illustrative configuration using placeholder URLs:

```json
{
  "registries": [
    {
      "id": "rpstack",
      "name": "RPStack",
      "url": "https://registry.example.org/rpstack/index.json",
      "enabled": true
    },
    {
      "id": "company",
      "name": "Company Robotics",
      "url": "https://robotics.example.com/registry/index.json",
      "credential_ref": "company-registry",
      "enabled": true
    }
  ]
}
```

Store credentials in the desktop credential store, not project files, manifests,
or devices. Scope credentials to their configured hosts; do not forward them to
arbitrary artifact URLs or redirects referenced by registry metadata.

Resolution follows these rules:

- A component is identified by registry identity, component ID, and version/build.
  Matching names from two registries remain distinct choices.
- Dependencies default to their originating registry. Cross-registry dependencies
  explicitly identify the other source, which the project maps to a configured URL.
- Never silently override a duplicate or use registry ordering to select code.
- Never substitute a public package for an unavailable private dependency.
- Record the selected source identity, URL, immutable revision, and hashes in the
  deployment lock. Disabling a source does not rewrite existing selections.

Private registry access is needed only on Architect. Devices receive resolved
files and their deployment manifest over the management connection.

## Refresh, caching, and offline use

Cache each registry and selected ref independently. Use conditional requests with
ETags where supported, validate downloaded metadata before replacing the cache,
and retain the last valid index when a source is unavailable. Expose the last
successful refresh and errors rather than implying that cached data is current.

A failed source does not block browsing other sources. Offline deployment is
possible only when all exact locked artifacts are cached and verified. Refreshing
the palette does not modify an existing deployment; adopting a new version is a
separate deployment change, whether manual or governed by an update policy.

## Integration with Robot Architect

Current Architect discovery scans local `component.yaml` files. Registry discovery
should become an additional source feeding that component palette. Local metadata
remains useful during development; identify it explicitly and capture its exact
contents when creating a deployment rather than presenting uncommitted code as a
published version.

See [Device provisioning and bootstrap](bootstrap.html) for delivery, inventory,
and readiness, and [Services level](services.html) for current capability contracts.

## External references

- [GitHub repository contents API](https://docs.github.com/en/rest/repos/contents): selecting a branch, tag, or commit with `ref`.
- [GitHub REST API best practices](https://docs.github.com/rest/guides/best-practices-for-integrators): conditional requests and caching.
