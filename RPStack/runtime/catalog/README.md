# Distributed robot catalog

Configure `{"id":"catalog","entry_point":"rpstack.catalog:Catalog"}` in
`runtime` on every participating node. Each catalog broadcasts its public node
profile on `_rp.catalog.profile` over the configured signal routes. Include
`mesh` (or another transport name) in `signals.routes` for network discovery;
`local` alone intentionally discovers only the local node. Nodes must use the
same entity and distinct node IDs. Relaying and radio channels follow the signal
and meshnet configuration. No static peer list or central gateway is required.

The profile includes service identity, selected implementation capabilities,
provided/consumed signals, declared apps, node state, and optional public
`composition` metadata. Configuration, constructors, resources, and Wi-Fi
credentials are excluded. Do not place secrets in `composition` or signals.
Capabilities are exposed as one entity-wide list with owning node/service IDs;
discovery does not automatically authorize remote execution or rebind hardware.

Default bounds: 16 nodes (including local), 8192 UTF-8 bytes per profile,
32 recent non-catalog remote signals. Profiles are split into bounded chunks,
announced every 5 seconds, and expire after 20 seconds without a complete profile.
Incomplete profiles expire too. Out-of-order chunks are assembled atomically;
duplicates, invalid shape, conflicting chunks, oversized profiles and capacity
overflow cannot grow storage without bounds. Each packet must fit the configured
signal `max_bytes`; startup checks the local profile and fails explicitly if not.
Catalog frames wait until selected outbound transport queues are empty, leaving
queue capacity for command/reply traffic. Transport backpressure is retried. Missing fragments are recovered by the next
periodic full announcement. Gateways have eventually consistent local views.

Constructor options: `interval_ms`, `ttl_ms` (greater than twice the interval and
at most 60000), `max_nodes`, `max_profile_bytes`, `message_limit`. Budget RAM for
both complete and partial profiles when increasing these values. Hardware heap,
radio congestion and discovery latency require device testing.

Physical composition models are provided by:
`rpstack.catalog.capabilities` (`PhysicalComponent`, `CompositeUnit`,
`RobotRequirements`, `CapabilityMatcher`, mount-claim helpers),
`rpstack.catalog.registry` (`CompositionRegistry`), and
`rpstack.catalog.schema`. Apps may use these models to build public `composition`
metadata. Composition reconciliation and node discovery are separate responsibilities.

Run host integration tests:

```sh
python3 -m unittest discover -s RPStack/runtime/catalog/test -v
```
