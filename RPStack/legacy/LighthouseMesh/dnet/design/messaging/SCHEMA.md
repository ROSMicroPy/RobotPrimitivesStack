# DistNet Messaging Protocol Schema

## Design Targets

- Nodes broadcast composition facts instead of registering with a single authority.
- Nodes also broadcast transient events for cross-node coordination.
- Any composition tracker can consume the same broadcast traffic and derive a local composition view.
- Claims are self-contained, versioned, ordered, and lease-based.
- The model is graph-first and works across humanoid, wheeled, quadruped, snake, and hybrid robots.
- The protocol is part-first, not service-first.

## Protocol Version

- `v` (int): protocol version, currently `2`

## Common Envelope

All protocol messages carry:

- `v` (int): protocol version
- `t` (str): message type
- `n` (str): node id
- `b` (str): boot/session id, changes whenever the node restarts
- `q` (int): monotonic sequence number within one boot
- `ts` (int): node-local timestamp in milliseconds or ticks

Example:

```json
{"v":2,"t":"c","n":"joint_a1b2","b":"8f02","q":2,"ts":1715000100}
```

## Message Types

### `a` - Announce

Lightweight liveness beacon.

Required fields:

- `v`, `t`, `n`, `b`, `q`, `ts`
- `ttl` (int): freshness window in milliseconds
- `pk` (str): part kind, such as `joint`, `wheel`, `segment`, `sensor`

Optional fields:

- `fw` (str): firmware version

Example:

```json
{"v":2,"t":"a","n":"joint_a1b2","b":"8f02","q":1,"ts":1715000000,"ttl":3000,"pk":"joint","fw":"0.1.0"}
```

### `c` - Composition Claim

Primary mount and trait registration message.

Required fields:

- `v`, `t`, `n`, `b`, `q`, `ts`
- `ttl` (int): claim freshness window in milliseconds
- `cid` (str): claim id unique within a node boot
- `part` (object): part traits
- `loc` (object): mounted location identity
- `state` (object): current runtime state

Example:

```json
{
  "v": 2,
  "t": "c",
  "n": "joint_a1b2",
  "b": "8f02",
  "q": 2,
  "ts": 1715000100,
  "ttl": 3000,
  "cid": "joint_a1b2:left_shoulder",
  "part": {
    "kind": "joint",
    "model": "servo_2axis_v1",
    "class": "articulated_joint",
    "dofs": [
      {"id": "pitch", "kind": "angular", "axis": "pitch", "min": -90, "max": 90, "unit": "deg"},
      {"id": "yaw", "kind": "angular", "axis": "yaw", "min": -120, "max": 120, "unit": "deg"}
    ],
    "coupling": "independent",
    "ctrl": ["position", "stop"],
    "fb": ["encoder"]
  },
  "loc": {
    "id": "left_shoulder",
    "parent": "torso_left_upper",
    "family": "shoulder",
    "src": "synthetic",
    "conf": 100
  },
  "state": {
    "cal": "ready",
    "health": "ok",
    "conf": 95
  }
}
```

### `u` - Composition Update

Refreshes or updates the state of an existing claim without resending the full trait model.

Required fields:

- `v`, `t`, `n`, `b`, `q`, `ts`
- `cid` (str): existing claim id
- `ttl` (int): refreshed claim freshness window
- `state` (object): updated runtime state

Example:

```json
{"v":2,"t":"u","n":"joint_a1b2","b":"8f02","q":3,"ts":1715001100,"cid":"joint_a1b2:left_shoulder","ttl":3000,"state":{"cal":"ready","health":"ok","conf":93}}
```

### `x` - Withdraw

Explicitly removes a claim.

Required fields:

- `v`, `t`, `n`, `b`, `q`, `ts`
- `cid` (str): claim id being withdrawn
- `reason` (str): reason code

Example:

```json
{"v":2,"t":"x","n":"joint_a1b2","b":"8f02","q":5,"ts":1715003000,"cid":"joint_a1b2:left_shoulder","reason":"shutdown"}
```

### `r` - Tracker Report

Optional tracker advisory message. This is not required for correctness.

Required fields:

- `v`, `t`, `n`, `b`, `q`, `ts`
- `subject` (str): node or claim identifier
- `status` (str): tracker interpretation, such as `accepted`, `conflict`, `stale`

Optional fields:

- `detail` (object): tracker-specific diagnostics

Example:

```json
{"v":2,"t":"r","n":"tracker_01","b":"trk17","q":200,"ts":1715004000,"subject":"joint_a1b2:left_shoulder","status":"conflict","detail":{"location_id":"left_shoulder","other_claimants":["joint_d9ff"]}}
```

### `e` - Event

Transient runtime event intended for cross-node observers.

Required fields:

- `v`, `t`, `n`, `b`, `q`, `ts`
- `event` (object): event payload

Required event payload fields:

- `name` (str): namespaced event name such as `vision.person_detected`
- `parameters` (object): event parameters

Optional event payload fields:

- `priority` (str): `low`, `normal`, `high`, or `critical`
- `ttl` (int): event freshness window in milliseconds

Example:

```json
{
  "v": 2,
  "t": "e",
  "n": "camera_01",
  "b": "91ab",
  "q": 17,
  "ts": 1715005000,
  "event": {
    "name": "vision.person_detected",
    "priority": "high",
    "ttl": 1000,
    "parameters": {
      "confidence": 92,
      "tracking_id": "p14"
    }
  }
}
```

## Schema Objects

### `part`

Describes intrinsic module traits. This object is intended to generalize beyond joints.

Required fields:

- `kind` (str): `joint`, `wheel`, `segment`, `sensor`, `power`, or another module kind

Common optional fields:

- `model` (str): hardware or firmware model identifier
- `class` (str): generic family identifier
- `ctrl` (array[str]): supported raw control modes
- `fb` (array[str]): supported feedback modes

Joint-oriented optional fields:

- `dofs` (array[object]): explicit DOF descriptors
- `coupling` (str): `independent`, `coupled`, or `mimic`

Example joint part:

```json
{
  "kind": "joint",
  "model": "servo_1axis_v1",
  "class": "simple_servo",
  "dofs": [
    {"id": "pitch", "kind": "angular", "axis": "pitch", "min": 0, "max": 180, "unit": "deg"}
  ],
  "coupling": "independent",
  "ctrl": ["position", "stop"],
  "fb": ["encoder"]
}
```

Example wheel part:

```json
{
  "kind": "wheel",
  "model": "wheel_drive_v2",
  "class": "drive_module",
  "dofs": [
    {"id": "roll", "kind": "continuous", "axis": "roll", "unit": "deg"}
  ],
  "ctrl": ["velocity", "stop"],
  "fb": ["encoder", "current"]
}
```

### `dof`

Explicit degrees of freedom are preferred over a single scalar `dof` count.

Recommended fields:

- `id` (str): axis identifier local to the part
- `kind` (str): `angular`, `linear`, or `continuous`
- `axis` (str): semantic axis label
- `min` (number): lower limit when bounded
- `max` (number): upper limit when bounded
- `unit` (str): unit such as `deg` or `mm`

Optional fields:

- `frame` (str): usually `local`
- `max_velocity` (number)
- `max_acceleration` (number)
- `resolution` (number)

Example:

```json
{"id":"pitch","kind":"angular","axis":"pitch","min":-90,"max":90,"unit":"deg"}
```

### `loc`

Describes mounted topology identity.

Required fields:

- `id` (str): unique mount slot identifier

Optional fields:

- `parent` (str): parent slot or structure identifier
- `family` (str): semantic family such as `shoulder`, `knee`, `segment_link`
- `src` (str): `synthetic`, `qr`, `nfc`, or `manual`
- `conf` (int): confidence `0..100`
- `orient` (str): coarse orientation hint

Example humanoid location:

```json
{"id":"left_knee","parent":"left_upper_leg","family":"knee","src":"synthetic","conf":90}
```

Example snake location:

```json
{"id":"segment_07_joint","parent":"segment_06_body","family":"segment_link","src":"nfc","conf":100}
```

### `state`

Represents runtime condition for an active claim.

Recommended fields:

- `cal` (str): `unknown`, `uncalibrated`, `calibrating`, `ready`, or `fault`
- `health` (str): `ok`, `degraded`, `fault`, or `offline`
- `conf` (int): node confidence `0..100`

Optional fields:

- `faults` (array[str])
- `temp` (number)
- `supply` (number)

Example:

```json
{"cal":"ready","health":"ok","conf":95}
```

## Protocol Rules

### Identity

- `n` uniquely identifies a node.
- `b` changes on restart and invalidates prior claims from the same `n`.
- `cid` uniquely identifies one active claim instance within a node boot.

### Ordering

- For the same `(n, b)`, greater `q` supersedes lower `q`.
- Duplicate messages are valid and should be processed idempotently.

### Freshness

- A claim remains active until `last_seen_ts + ttl`.
- If no refresh arrives before expiry, trackers mark the claim stale and remove it from the active composition graph.
- An event with `event.ttl` is considered stale after `ts + event.ttl`.

### Conflict Handling

If multiple active claims target the same `loc.id`:

- Trackers preserve all raw claims.
- Trackers mark the location as conflicted.
- Trackers may compute a preferred active claim with a deterministic tie-break.

Recommended tie-break order:

1. Higher `loc.conf`
2. Stronger `loc.src`: `nfc > qr > manual > synthetic`
3. Higher `state.conf`
4. Lexical `n`

### Replacement

- A new `c` message from the same node may supersede an older `cid`.
- If a node remounts, it should emit `x` for the old claim and `c` for the new claim.

## Derived Semantics

Nodes publish raw part mechanics and mounted location identity.
Trackers or higher-level planners derive semantic robot interfaces from the assembled composition graph.

Events are separate from composition facts:

- composition messages are persistent assertions about robot structure
- event messages are transient observations or triggers
- listeners may react to an event, cache it briefly, or ignore it entirely

Examples:

- Node-level raw mechanic: `pitch` and `yaw` angular DOFs
- Tracker-level semantic role: `left_shoulder`
- Planner-level meaning: `arm aim`, `reach`, `gait`, or `snake bend sequence`

## Migration Note

This schema replaces the earlier service-discovery protocol described in the legacy `src/messaging/SCHEMA.md`.
