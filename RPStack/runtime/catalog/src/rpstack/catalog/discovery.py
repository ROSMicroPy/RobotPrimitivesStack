"""Bounded, entity-scoped node and capability discovery over RPStack signals."""
from rpstack.support import asyncio, json, now_ms, elapsed_ms
from rpstack.signals.model import encode

CATALOG_SIGNAL = '_rp.catalog.profile'


class Catalog:
    # Validate discovery limits and prepare bounded storage for nodes, fragments, and messages.
    def __init__(self, node, interval_ms=5000, ttl_ms=20000, max_nodes=16,
                 max_profile_bytes=8192, message_limit=32):
        if any(type(v) is not int or v < 1 for v in
               (interval_ms, ttl_ms, max_nodes, max_profile_bytes, message_limit)):
            raise ValueError('catalog limits must be positive integers')
        if ttl_ms <= interval_ms * 2 or ttl_ms > 60000:
            raise ValueError('catalog TTL must exceed two announcement intervals and be <= 60000')
        self.node = node
        self.interval_ms, self.ttl_ms = interval_ms, ttl_ms
        self.max_nodes, self.max_profile_bytes = max_nodes, max_profile_bytes
        self.message_limit = message_limit
        self.nodes, self.pending, self.messages = {}, {}, []
        self.stats = {'invalid': 0, 'overflow': 0, 'announced': 0}
        self.subscription = None
        self.revision = 0

    # Project this node's public services and composition into a shareable discovery profile.
    def profile(self):
        discovery = self.node.discovery()
        services = {}
        for name, service in discovery['services'].items():
            services[name] = {key: service[key] for key in
                ('name', 'type', 'version', 'capabilities', 'signals') if key in service}
        for definition in self.node.registry.definitions():
            caps = dict(services[definition.service_id].get('capabilities', {}))
            caps['provides'] = definition.provides
            services[definition.service_id]['capabilities'] = caps
        return {'node_id': self.node.signals.node_id, 'name': discovery['name'],
                'services': services, 'apps': discovery['apps'],
                'composition': self.node.document.get('composition', {}),
                'state': self.node.state}

    # Discard stale remote profiles and incomplete assemblies after their TTL.
    def _prune(self):
        for key, record in tuple(self.nodes.items()):
            if elapsed_ms(record['seen']) >= self.ttl_ms:
                del self.nodes[key]
        for key, record in tuple(self.pending.items()):
            if elapsed_ms(record['seen']) >= self.ttl_ms:
                del self.pending[key]

    # Refresh the local node's profile and last-seen timestamp.
    def _local(self):
        self.nodes[self.node.signals.node_id] = {'profile': self.profile(),
            'seen': now_ms(), 'boot': self.node.signals.boot, 'sequence': 0}

    # Refresh discovery state and flatten advertised capabilities for consumers browsing the
    # catalog.
    def snapshot(self):
        self._prune()
        self._local()
        nodes, capabilities = [], []
        for key in sorted(self.nodes):
            record = self.nodes[key]
            profile = dict(record['profile'])
            profile['age_ms'] = max(0, elapsed_ms(record['seen']))
            profile['local'] = key == self.node.signals.node_id
            nodes.append(profile)
            for service_id, service in profile['services'].items():
                for capability in service.get('capabilities', {}).get('provides', []):
                    capabilities.append({'node': key, 'service': service_id, 'capability': capability})
        return {'version': 'rp.catalog/v1', 'entity': self.node.signals.entity,
                'gateway_node': self.node.signals.node_id, 'count': len(nodes),
                'nodes': nodes, 'capabilities': capabilities}

    # Split the public profile into revisioned fragments and verify every frame fits the signal
    # limit.
    def frames(self):
        text = json.dumps(self.profile())
        if len(text.encode('utf-8')) > self.max_profile_bytes:
            raise ValueError('local catalog profile exceeds max_profile_bytes')
        self.revision += 1
        chunks = [text[i:i + 64] for i in range(0, len(text), 64)]
        frames = [{'revision': self.revision, 'index': i, 'count': len(chunks), 'data': chunk}
                  for i, chunk in enumerate(chunks)]
        # Fail at startup for an incompatible signal byte limit, before broadcasting partial data.
        for payload in frames:
            encode({'version': 1, 'entity': self.node.signals.entity, 'source': self.node.signals.node_id,
                    'boot': self.node.signals.boot, 'sequence': 2147483647, 'name': CATALOG_SIGNAL,
                    'target': '*', 'payload': payload, 'correlation': None, 'hops': 8,
                    'ttl_ms': self.ttl_ms}, self.node.signals.max_bytes)
        return frames

    # Collect ordinary messages or assemble validated catalog fragments into remote node
    # profiles.
    def ingest(self, signal):
        if signal.get('entity') != self.node.signals.entity or signal.get('source') == self.node.signals.node_id:
            return
        if signal.get('name') != CATALOG_SIGNAL:
            self.messages.append(signal)
            del self.messages[:-self.message_limit]
            return
        self._prune()
        try:
            source, boot, payload = signal['source'], signal['boot'], signal['payload']
            revision, index, count, data = (payload[k] for k in ('revision', 'index', 'count', 'data'))
            if any(type(v) is not int for v in (revision, index, count)) or revision < 1:
                raise ValueError('invalid profile revision')
            if not 0 <= index < count <= (self.max_profile_bytes + 63) // 64 or not isinstance(data, str) or not 1 <= len(data) <= 64:
                raise ValueError('invalid profile chunk')
            record = self.nodes.get(source)
            if record and boot in record.get('retired', []):
                return
            if record and record['boot'] == boot and signal['sequence'] <= record['sequence']:
                return
            assembly = self.pending.get(source)
            if assembly and assembly['boot'] == boot and revision < assembly['revision']:
                return
            if not assembly or (assembly['boot'], assembly['revision']) != (boot, revision):
                if source not in self.pending and len(self.pending) >= self.max_nodes:
                    raise ValueError('pending catalog capacity reached')
                assembly = {'boot': boot, 'revision': revision, 'count': count, 'parts': {},
                            'size': 0, 'seen': now_ms(), 'sequence': 0}
                self.pending[source] = assembly
            if assembly['count'] != count:
                raise ValueError('conflicting profile chunk count')
            if index in assembly['parts']:
                if assembly['parts'][index] != data:
                    raise ValueError('conflicting profile chunk')
                return
            assembly['size'] += len(data.encode('utf-8'))
            if assembly['size'] > self.max_profile_bytes:
                del self.pending[source]
                raise ValueError('profile exceeds byte limit')
            assembly['parts'][index] = data
            assembly['sequence'] = max(assembly['sequence'], signal['sequence'])
            if len(assembly['parts']) != count:
                return
            del self.pending[source]
            profile = json.loads(''.join(assembly['parts'][i] for i in range(count)))
            if not isinstance(profile, dict) or profile.get('node_id') != source:
                raise ValueError('profile identity mismatch')
            if not isinstance(profile.get('services'), dict) or not isinstance(profile.get('apps'), list):
                raise ValueError('invalid profile services/apps')
            if not isinstance(profile.get('name'), str) or not isinstance(profile.get('state'), str):
                raise ValueError('invalid profile name/state')
            for app in profile['apps']:
                if not isinstance(app, dict) or not all(isinstance(app.get(k), str) for k in ('id', 'entry_point')):
                    raise ValueError('invalid app identity')
            for service in profile['services'].values():
                if not isinstance(service, dict) or any(k in service and not isinstance(service[k], str) for k in ('name', 'type', 'version')):
                    raise ValueError('invalid service identity')
                caps = service.get('capabilities', {})
                if not isinstance(caps, dict) or not isinstance(caps.get('provides', []), list):
                    raise ValueError('invalid capabilities')
            self._local()
            if source not in self.nodes and len(self.nodes) >= self.max_nodes:
                raise ValueError('node catalog capacity reached')
            retired = list(record.get('retired', [])) if record else []
            if record and record['boot'] != boot:
                retired.append(record['boot'])
            self.nodes[source] = {'profile': profile, 'boot': boot, 'retired': retired[-4:],
                'sequence': assembly['sequence'], 'seen': now_ms()}
        except (ValueError, KeyError, TypeError, AttributeError):
            self.stats['invalid'] += 1

    # Validate outbound frames and register the local profile before subscribing to discovery
    # traffic.
    async def start(self):
        self.frames()  # validate public projection before any background work
        self._local()
        self.subscription = self.node.signals.subscribe('*')

    # Consume discovery traffic and periodically announce fragments while leaving transport
    # space for commands.
    async def run(self):
        frames, last = [], None
        while True:
            if self.subscription.overflow:
                self.subscription.overflow = False
                self.stats['overflow'] += 1
            while self.subscription.items:
                signal, received = self.subscription.items.pop(0)
                if elapsed_ms(received) < signal['ttl_ms']:
                    self.ingest(signal)
            self.subscription.ready.clear()
            if not frames and (last is None or elapsed_ms(last) >= self.interval_ms):
                frames = self.frames()
                last = now_ms()
            # Catalog profiles are background traffic. Keep the transport queue
            # available for command replies instead of filling it with fragments.
            if frames and all(not port['queue'] for name, port in self.node.signals.ports.items()
                              if name in self.node.signals.routes):
                try:
                    self.node.signals.publish(CATALOG_SIGNAL, frames[0], ttl_ms=self.ttl_ms)
                    frames.pop(0)
                    self.stats['announced'] += 1
                except RuntimeError:
                    pass  # bounded transport backpressure; retry on next tick
            self._prune()
            await asyncio.sleep(0.01)

    # Close discovery subscriptions and discard incomplete remote profile assemblies.
    async def stop(self):
        if self.subscription:
            self.subscription.close()
        self.pending.clear()
