"""Entity-scoped local delivery, bounded transport queues and loop suppression."""
from .model import asyncio, now_ms, elapsed, nonce, encode, decode


class Subscription:
    def __init__(self, bus, name, correlation=None, source=None):
        self.bus, self.name, self.correlation, self.source = bus, name, correlation, source
        self.items = []
        self.ready = asyncio.Event()
        self.overflow = False

    async def get(self, timeout=None):
        async def receive():
            while True:
                while not self.items and not self.overflow:
                    await self.ready.wait()
                if self.overflow:
                    raise RuntimeError("signal queue overflow: " + self.name)
                signal, received = self.items.pop(0)
                if not self.items:
                    self.ready.clear()
                if elapsed(received) < signal["ttl_ms"]:
                    return signal
        return await receive() if timeout is None else await asyncio.wait_for(receive(), timeout)

    def close(self):
        subscribers = self.bus.subscribers.get(self.name, [])
        if self in subscribers:
            subscribers.remove(self)
        if not subscribers:
            self.bus.subscribers.pop(self.name, None)


class SignalBus:
    def __init__(self, entity="local", node_id="local", queue_limit=16,
                 routes=None, bridges=None, seen_limit=512, max_bytes=2048):
        if any(type(value) is not int for value in (queue_limit, seen_limit, max_bytes)) or queue_limit < 1 or seen_limit < 1 or max_bytes < 128:
            raise ValueError("invalid signal limits")
        self.entity, self.node_id, self.boot = entity, node_id, nonce()
        self.queue_limit, self.seen_limit, self.max_bytes = queue_limit, seen_limit, max_bytes
        self.routes = list(routes if routes is not None else ["local"])
        self.bridges = bridges or {}
        self.subscribers = {}
        self.ports = {}
        self.seen = {}
        self.sequence = 0
        self.stats = {"published": 0, "received": 0, "duplicate": 0, "foreign": 0,
                      "invalid": 0, "dropped": 0, "sent": 0}

    def validate_configuration(self):
        # Validate identities even on local-only nodes, before touching hardware.
        encode({'version': 1, 'entity': self.entity, 'source': self.node_id, 'boot': self.boot,
                'sequence': 1, 'name': 'validate', 'target': '*', 'payload': None,
                'correlation': None, 'hops': 0, 'ttl_ms': 1}, self.max_bytes)
        self._check_routes(self.routes)
        for ingress, routes in self.bridges.items():
            if ingress not in self.ports:
                raise ValueError('unknown bridge ingress: ' + ingress)
            self._check_routes(routes)

    def subscribe(self, name, correlation=None, source=None):
        sub = Subscription(self, name, correlation, source)
        self.subscribers.setdefault(name, []).append(sub)
        return sub

    def add_transport(self, name, transport, relay=False):
        if not isinstance(name, str) or not name or type(relay) is not bool:
            raise ValueError("invalid transport name or relay option")
        if name == "local" or name in self.ports:
            raise ValueError("duplicate/reserved transport name")
        self.ports[name] = {"transport": transport, "relay": relay, "queue": [],
                            "ready": asyncio.Event()}

    def _remember(self, signal):
        # A sliding replay window bounds memory per origin, not per signal rate.
        # Packets more than 63 positions behind the highest sequence are stale.
        for key, record in tuple(self.seen.items()):
            if elapsed(record['updated']) >= 60000:
                del self.seen[key]
        key = (signal['source'], signal['boot'])
        sequence = signal['sequence']
        record = self.seen.get(key)
        if record is None:
            if len(self.seen) >= self.seen_limit:
                raise RuntimeError('signal deduplication capacity reached')
            self.seen[key] = {'highest': sequence, 'bits': 1, 'updated': now_ms()}
            return True
        offset = record['highest'] - sequence
        if offset >= 64 or (offset >= 0 and record['bits'] & (1 << offset)):
            self.stats['duplicate'] += 1
            return False
        if offset < 0:
            shift = -offset
            record['bits'] = 1 if shift >= 64 else ((record['bits'] << shift) | 1) & ((1 << 64) - 1)
            record['highest'] = sequence
        else:
            record['bits'] |= 1 << offset
        record['updated'] = now_ms()
        return True

    def _deliver(self, signal):
        if signal["target"] not in ("*", self.node_id):
            return
        subscribers = list(self.subscribers.get(signal["name"], [])) + list(self.subscribers.get("*", []))
        for sub in subscribers:
            if sub.correlation is not None and sub.correlation != signal["correlation"]:
                continue
            if sub.source is not None and sub.source != signal["source"]:
                continue
            if len(sub.items) >= self.queue_limit:
                sub.overflow = True
                self.stats["dropped"] += 1
            else:
                # Isolate subscribers from one another's payload mutations.
                sub.items.append((decode(encode(signal, self.max_bytes), self.max_bytes), now_ms()))
            sub.ready.set()

    def _check_routes(self, routes):
        if not isinstance(routes, (list, tuple)) or not all(isinstance(route, str) for route in routes):
            raise ValueError('signal routes must be a list of names')
        if len(set(routes)) != len(routes):
            raise ValueError("duplicate signal route")
        for route in routes:
            if route != "local":
                if route not in self.ports:
                    raise ValueError("unknown signal route: " + route)
                if len(self.ports[route]["queue"]) >= self.queue_limit:
                    raise RuntimeError("signal transport queue full: " + route)

    def _enqueue(self, signal, routes):
        for route in routes:
            if route != "local":
                port = self.ports[route]
                port["queue"].append((decode(encode(signal, self.max_bytes), self.max_bytes), now_ms()))
                port["ready"].set()

    def publish(self, name, payload=None, *, correlation=None, target="*", routes=None,
                ttl_ms=10000, hops=8):
        routes = self.routes if routes is None else routes
        self._check_routes(routes)
        sequence = self.sequence + 1
        signal = {"version": 1, "entity": self.entity, "source": self.node_id,
                  "boot": self.boot, "sequence": sequence, "name": name, "payload": payload,
                  "target": target, "correlation": correlation, "hops": hops, "ttl_ms": ttl_ms}
        signal = decode(encode(signal, self.max_bytes), self.max_bytes)
        if not self._remember(signal):
            raise RuntimeError("signal identity collision")
        self.sequence = sequence
        self._enqueue(signal, routes)
        if "local" in routes:
            self._deliver(signal)
        self.stats["published"] += 1
        return signal

    def receive(self, data, ingress):
        try:
            signal = decode(data, self.max_bytes)
        except (ValueError, TypeError, UnicodeError):
            self.stats["invalid"] += 1
            return False
        if signal["entity"] != self.entity:
            self.stats["foreign"] += 1
            return False
        if not self._remember(signal):
            return False
        self._deliver(signal)
        self.stats["received"] += 1
        if signal["hops"]:
            routes = list(self.bridges.get(ingress, []))
            if self.ports[ingress]["relay"] and ingress not in routes:
                routes.append(ingress)
            forwarded = dict(signal)
            forwarded["hops"] -= 1
            # Receive is best effort: one congested egress must not block local delivery.
            for route in routes:
                try:
                    self._check_routes([route])
                    self._enqueue(forwarded, [route])
                except RuntimeError:
                    self.stats["dropped"] += 1
        return True

    async def transmit(self, name):
        port = self.ports[name]
        while True:
            await port["ready"].wait()
            while port["queue"]:
                signal, queued = port["queue"].pop(0)
                signal["ttl_ms"] -= elapsed(queued)
                if signal["ttl_ms"] > 0:
                    await port["transport"].send(encode(signal, self.max_bytes))
                    self.stats["sent"] += 1
                else:
                    self.stats["dropped"] += 1
                await asyncio.sleep(0)
            port["ready"].clear()

    async def listen(self, name):
        transport = self.ports[name]["transport"]
        while True:
            data = await transport.recv()
            self.receive(data, name)
            await asyncio.sleep(0)

    def clear_pending(self):
        for port in self.ports.values():
            port["queue"].clear()
            port["ready"].clear()
