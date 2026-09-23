import time

from .schema import Schema


class CompositionRegistry:
    """In-memory registry for composition claims and tracker observations."""

    SOURCE_PRIORITY = {
        Schema.LOCATION_SYNTHETIC: 0,
        Schema.LOCATION_MANUAL: 1,
        Schema.LOCATION_QR: 2,
        Schema.LOCATION_NFC: 3,
    }

    def __init__(self):
        self._nodes = {}
        self._claims = {}
        self._node_claims = {}
        self._reports = []
        self._events = []

    def register_announce(self, msg, seen_at_ms=None):
        seen_at_ms = self._normalize_seen_at(seen_at_ms)
        node_id = msg[Schema.F_NODE_ID]
        boot_id = msg[Schema.F_BOOT_ID]
        sequence = msg[Schema.F_SEQUENCE]
        existing = self._nodes.get(node_id)
        if not self._is_newer(existing, boot_id, sequence):
            return False

        if existing and existing.get("boot_id") != boot_id:
            self._drop_node_claims(node_id)

        self._nodes[node_id] = {
            "node_id": node_id,
            "boot_id": boot_id,
            "last_sequence": sequence,
            "last_seen_ms": seen_at_ms,
            "timestamp_ms": msg[Schema.F_TIMESTAMP],
            "ttl_ms": msg[Schema.F_TTL],
            "part_kind": msg[Schema.F_PART_KIND],
            "firmware": msg.get(Schema.F_FIRMWARE),
            "announce": dict(msg),
        }
        return True

    def register_claim(self, msg, seen_at_ms=None):
        seen_at_ms = self._normalize_seen_at(seen_at_ms)
        node_id = msg[Schema.F_NODE_ID]
        boot_id = msg[Schema.F_BOOT_ID]
        sequence = msg[Schema.F_SEQUENCE]
        node = self._nodes.get(node_id)
        if not self._is_newer(node, boot_id, sequence):
            return False

        if node and node.get("boot_id") != boot_id:
            self._drop_node_claims(node_id)

        self._nodes[node_id] = {
            "node_id": node_id,
            "boot_id": boot_id,
            "last_sequence": sequence,
            "last_seen_ms": seen_at_ms,
            "timestamp_ms": msg[Schema.F_TIMESTAMP],
            "ttl_ms": msg[Schema.F_TTL],
            "part_kind": msg[Schema.F_PART].get(Schema.F_KIND),
            "firmware": node.get("firmware") if node else None,
            "announce": node.get("announce") if node else None,
        }

        claim_id = msg[Schema.F_CLAIM_ID]
        claim = {
            "claim_id": claim_id,
            "node_id": node_id,
            "boot_id": boot_id,
            "sequence": sequence,
            "timestamp_ms": msg[Schema.F_TIMESTAMP],
            "last_seen_ms": seen_at_ms,
            "ttl_ms": msg[Schema.F_TTL],
            "part": dict(msg[Schema.F_PART]),
            "location": dict(msg[Schema.F_LOCATION]),
            "state": dict(msg[Schema.F_STATE]),
            "active": True,
            "withdrawn": False,
        }
        self._claims[claim_id] = claim
        self._node_claims.setdefault(node_id, set()).add(claim_id)
        return True

    def register_update(self, msg, seen_at_ms=None):
        seen_at_ms = self._normalize_seen_at(seen_at_ms)
        node_id = msg[Schema.F_NODE_ID]
        boot_id = msg[Schema.F_BOOT_ID]
        sequence = msg[Schema.F_SEQUENCE]
        node = self._nodes.get(node_id)
        if not self._is_newer(node, boot_id, sequence):
            return False

        claim_id = msg[Schema.F_CLAIM_ID]
        claim = self._claims.get(claim_id)
        if claim is None:
            return False
        if claim["node_id"] != node_id or claim["boot_id"] != boot_id:
            return False

        claim["sequence"] = sequence
        claim["timestamp_ms"] = msg[Schema.F_TIMESTAMP]
        claim["last_seen_ms"] = seen_at_ms
        claim["ttl_ms"] = msg[Schema.F_TTL]
        claim["state"] = dict(msg[Schema.F_STATE])
        claim["active"] = True
        claim["withdrawn"] = False

        self._nodes[node_id] = {
            "node_id": node_id,
            "boot_id": boot_id,
            "last_sequence": sequence,
            "last_seen_ms": seen_at_ms,
            "timestamp_ms": msg[Schema.F_TIMESTAMP],
            "ttl_ms": msg[Schema.F_TTL],
            "part_kind": claim["part"].get(Schema.F_KIND),
            "firmware": node.get("firmware") if node else None,
            "announce": node.get("announce") if node else None,
        }
        return True

    def register_withdraw(self, msg, seen_at_ms=None):
        seen_at_ms = self._normalize_seen_at(seen_at_ms)
        node_id = msg[Schema.F_NODE_ID]
        boot_id = msg[Schema.F_BOOT_ID]
        sequence = msg[Schema.F_SEQUENCE]
        node = self._nodes.get(node_id)
        if not self._is_newer(node, boot_id, sequence):
            return False

        claim_id = msg[Schema.F_CLAIM_ID]
        claim = self._claims.get(claim_id)
        if claim is None:
            return False
        if claim["node_id"] != node_id or claim["boot_id"] != boot_id:
            return False

        claim["sequence"] = sequence
        claim["timestamp_ms"] = msg[Schema.F_TIMESTAMP]
        claim["last_seen_ms"] = seen_at_ms
        claim["active"] = False
        claim["withdrawn"] = True
        claim["reason"] = msg[Schema.F_REASON]

        self._nodes[node_id] = {
            "node_id": node_id,
            "boot_id": boot_id,
            "last_sequence": sequence,
            "last_seen_ms": seen_at_ms,
            "timestamp_ms": msg[Schema.F_TIMESTAMP],
            "ttl_ms": node.get("ttl_ms") if node else None,
            "part_kind": node.get("part_kind") if node else None,
            "firmware": node.get("firmware") if node else None,
            "announce": node.get("announce") if node else None,
        }
        return True

    def register_report(self, msg, seen_at_ms=None):
        seen_at_ms = self._normalize_seen_at(seen_at_ms)
        report = dict(msg)
        report["seen_at_ms"] = seen_at_ms
        self._reports.append(report)
        return True

    def register_event(self, msg, seen_at_ms=None):
        seen_at_ms = self._normalize_seen_at(seen_at_ms)
        event = dict(msg)
        event["seen_at_ms"] = seen_at_ms
        event_name = event[Schema.F_EVENT][Schema.F_EVENT_NAME]
        event["event_name"] = event_name
        event["expired"] = False
        self._events.append(event)
        return True

    def get_claim(self, claim_id, now_ms=None):
        self.prune_expired(now_ms=now_ms)
        claim = self._claims.get(claim_id)
        if claim is None:
            return None
        return dict(claim)

    def get_node(self, node_id):
        node = self._nodes.get(node_id)
        if node is None:
            return None
        return dict(node)

    def active_claims(self, now_ms=None):
        self.prune_expired(now_ms=now_ms)
        claims = []
        for claim in self._claims.values():
            if claim.get("active"):
                claims.append(dict(claim))
        claims.sort(key=lambda item: (item["location"].get(Schema.F_LOCATION_ID, ""), item["node_id"]))
        return claims

    def claims_for_location(self, location_id, now_ms=None):
        matches = []
        for claim in self.active_claims(now_ms=now_ms):
            if claim["location"].get(Schema.F_LOCATION_ID) == location_id:
                matches.append(claim)
        return matches

    def resolve_location(self, location_id, now_ms=None):
        claims = self.claims_for_location(location_id, now_ms=now_ms)
        if not claims:
            return {"location_id": location_id, "status": "empty", "claims": [], "winner": None}
        winner = max(claims, key=self._claim_priority)
        status = "active"
        if len(claims) > 1:
            status = "conflict"
        return {
            "location_id": location_id,
            "status": status,
            "claims": claims,
            "winner": dict(winner),
        }

    def all_locations(self, now_ms=None):
        self.prune_expired(now_ms=now_ms)
        location_ids = {}
        for claim in self._claims.values():
            if not claim.get("active"):
                continue
            location_id = claim["location"].get(Schema.F_LOCATION_ID)
            if location_id:
                location_ids[location_id] = True
        results = []
        for location_id in sorted(location_ids):
            results.append(self.resolve_location(location_id, now_ms=now_ms))
        return results

    def reports(self):
        return [dict(item) for item in self._reports]

    def events(self, event_name=None, now_ms=None, include_expired=False):
        self.prune_expired(now_ms=now_ms)
        results = []
        for event in self._events:
            if event_name is not None and event.get("event_name") != event_name:
                continue
            if not include_expired and event.get("expired"):
                continue
            results.append(dict(event))
        return results

    def latest_event(self, event_name=None, now_ms=None, include_expired=False):
        events = self.events(
            event_name=event_name,
            now_ms=now_ms,
            include_expired=include_expired,
        )
        if not events:
            return None
        return events[-1]

    def prune_expired(self, now_ms=None):
        now_ms = self._normalize_seen_at(now_ms)
        for claim in self._claims.values():
            if not claim.get("active"):
                continue
            expires_at = claim["last_seen_ms"] + claim["ttl_ms"]
            if expires_at <= now_ms:
                claim["active"] = False
                claim["expired"] = True
        for event in self._events:
            payload = event.get(Schema.F_EVENT) or {}
            ttl_ms = payload.get(Schema.F_EVENT_TTL)
            if ttl_ms is None:
                continue
            expires_at = int(event[Schema.F_TIMESTAMP]) + ttl_ms
            if expires_at <= now_ms:
                event["expired"] = True

    def _drop_node_claims(self, node_id):
        claim_ids = list(self._node_claims.get(node_id, set()))
        for claim_id in claim_ids:
            claim = self._claims.get(claim_id)
            if claim is not None:
                claim["active"] = False
                claim["superseded"] = True
        self._node_claims[node_id] = set()

    @classmethod
    def _claim_priority(cls, claim):
        location = claim.get("location") or {}
        state = claim.get("state") or {}
        source = location.get(Schema.F_LOCATION_SOURCE, Schema.LOCATION_SYNTHETIC)
        return (
            int(location.get(Schema.F_LOCATION_CONFIDENCE, 0) or 0),
            cls.SOURCE_PRIORITY.get(source, -1),
            int(state.get(Schema.F_STATE_CONFIDENCE, 0) or 0),
            claim.get("node_id", ""),
        )

    @staticmethod
    def _is_newer(existing, boot_id, sequence):
        if existing is None:
            return True
        existing_boot = existing.get("boot_id")
        existing_sequence = int(existing.get("last_sequence", -1))
        if existing_boot != boot_id:
            return True
        return int(sequence) > existing_sequence

    @staticmethod
    def _normalize_seen_at(seen_at_ms):
        if seen_at_ms is None:
            return int(time.time() * 1000)
        return int(seen_at_ms)
