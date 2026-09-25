"""One workflow coordinator dispatches leased, correlated actions to peer nodes."""
from rpstack.support import asyncio, now_ms, elapsed_ms
from rpstack.signals.model import nonce, plain


class RemoteActions:
    # Validate peers and limits, then prepare leased remote calls and observed workflow states.
    def __init__(self, node, peers, expose, lease_ms=3000, capacity=64):
        if type(lease_ms) is not int or type(capacity) is not int or not 100 <= lease_ms <= 10000 or not 1 <= capacity <= 256:
            raise ValueError('invalid remote action limits')
        for names in (peers, expose):
            if not isinstance(names, list) or not all(isinstance(name, str) and name for name in names) or len(set(names)) != len(names):
                raise ValueError('execution peers/expose must be lists of unique names')
        self.node, self.bus = node, node.signals
        self.peers, self.expose = set(peers), set(expose)
        self.lease_ms, self.capacity = lease_ms, capacity
        self.records = {}
        self.states = {}
        self.epoch = nonce()
        self.subscriptions = []

    # Subscribe to execution protocol messages before workflows can issue remote calls.
    def start(self):
        # Establish subscriptions synchronously before autostarting workflows.
        for name in ('state', 'probe', 'call', 'renew', 'cancel'):
            self.subscriptions.append(self.bus.subscribe('_rp.' + name))

    # Publish a correlated protocol message with a TTL bounded by the action lease.
    def _send(self, name, target, correlation, payload):
        return self.bus.publish('_rp.' + name, payload, target=target,
                                correlation=correlation, ttl_ms=min(self.lease_ms, 1000))

    # Negotiate the peer's epoch, issue one call, and renew its lease while awaiting a result.
    async def invoke(self, target, service, operation, arguments, run_id, timeout_s=30):
        if target not in self.peers:
            raise ValueError('undeclared execution peer: ' + target)
        correlation = run_id + '/' + nonce()
        sub = self.bus.subscribe('_rp.result', correlation=correlation, source=target)
        started = now_ms()
        ready = self.bus.subscribe('_rp.ready', correlation=correlation, source=target)
        try:
            self._send('probe', target, correlation, None)
            handshake = await ready.get(min(timeout_s, self.lease_ms / 1000))
            epoch = handshake['payload']['epoch']
            self._send('call', target, correlation, {'service': service, 'operation': operation,
                       'arguments': arguments, 'lease_ms': self.lease_ms, 'epoch': epoch})
            while True:
                remaining = timeout_s - elapsed_ms(started) / 1000
                if remaining <= 0:
                    raise TimeoutError('remote action timed out')
                try:
                    response = await sub.get(min(remaining, self.lease_ms / 3000))
                except asyncio.TimeoutError:
                    if elapsed_ms(started) >= timeout_s * 1000:
                        raise TimeoutError('remote action timed out')
                    self._send('renew', target, correlation, None)
                    continue
                payload = response['payload']
                if not isinstance(payload, dict) or 'ok' not in payload:
                    raise ValueError('invalid remote result')
                if not payload['ok']:
                    raise RuntimeError(payload.get('error', 'remote action failed'))
                return payload.get('result')
        finally:
            sub.close()
            ready.close()
            try:
                self._send('cancel', target, correlation, None)
            except (RuntimeError, ValueError):
                pass  # Receiver lease still bounds execution if cancellation is lost.

    # Invoke an exposed local operation and retain/send a compact success or failure response.
    async def _execute(self, key, record, payload):
        result = None
        try:
            if payload.get('service') not in self.expose:
                raise ValueError('service is not exposed for remote execution')
            result = {'ok': True, 'result': plain(await self.node.invoke(
                payload['service'], payload['operation'], payload.get('arguments', {})))}
        except asyncio.CancelledError:
            result = {'ok': False, 'error': 'remote action cancelled or lease expired'}
            raise
        except Exception as error:
            result = {'ok': False, 'error': str(error)[:256]}
        finally:
            record['result'], record['finished'] = result, now_ms()
            try:
                self._send('result', key[0], key[2], result)
            except (ValueError, RuntimeError):
                # Oversized results must still return a small, useful failure.
                try:
                    self._send('result', key[0], key[2], {'ok': False, 'error': 'result could not be delivered'})
                except (ValueError, RuntimeError):
                    pass

    # Validate protocol traffic and dispatch state updates, handshakes, calls, renewals, and
    # cancellations.
    async def _message(self, signal):
        if signal['name'] == '_rp.state':
            payload = signal['payload']
            if signal['source'] not in self.peers or not isinstance(payload, dict):
                return
            run = payload.get('run_id')
            revision = payload.get('revision')
            if run != signal['correlation'] or not isinstance(run, str) or type(revision) is not int:
                return
            if payload.get('state') not in ('pending', 'running', 'waiting', 'succeeded', 'failed', 'cancelled'):
                return
            key = (signal['source'], signal['boot'], run)
            previous = self.states.get(key)
            if previous is not None and previous['revision'] >= revision:
                return
            if previous is None and len(self.states) >= self.capacity:
                oldest = min(self.states, key=lambda k: self.states[k]['received'])
                del self.states[oldest]
            self.states[key] = dict(payload, coordinator=signal['source'], received=now_ms())
            return
        if signal['source'] not in self.peers or signal['target'] != self.bus.node_id or not signal['correlation']:
            return
        key = (signal['source'], signal['boot'], signal['correlation'])
        kind = signal['name']
        if kind == '_rp.probe':
            if self.node.accepting:
                self._send('ready', signal['source'], signal['correlation'], {'epoch': self.epoch})
            return
        record = self.records.get(key)
        if kind == '_rp.cancel':
            if record and record.get('task') in self.node.tasks.records:
                await self.node.tasks.cancel(record['task'])
            if record is None and len(self.records) < self.capacity:
                self.records[key] = {'finished': now_ms(), 'result': {'ok': False, 'error': 'cancelled'}}
            return
        if kind == '_rp.renew':
            if record and record.get('finished') is None:
                record['renewed'] = now_ms()
            return
        if record:
            if record.get('result') is not None:
                self._send('result', key[0], key[2], record['result'])
            return
        if len(self.records) >= self.capacity:
            self._send('result', key[0], key[2], {'ok': False, 'error': 'remote history capacity reached'})
            return
        payload = signal['payload']
        if not isinstance(payload, dict):
            return
        if payload.get('epoch') != self.epoch or not self.node.accepting:
            self._send('result', key[0], key[2], {'ok': False, 'error': 'remote node stopped or reset'})
            return
        lease = payload.get('lease_ms', self.lease_ms)
        if isinstance(lease, bool) or not isinstance(lease, int) or not 100 <= lease <= self.lease_ms:
            self._send('result', key[0], key[2], {'ok': False, 'error': 'invalid lease'})
            return
        record = {'renewed': now_ms(), 'lease': lease, 'finished': None, 'result': None}
        self.records[key] = record
        try:
            record['task'] = self.node.tasks.spawn('remote:' + key[2], self._execute, key, record, payload,
                                                    kind='flow', owner=key[0])
        except RuntimeError as error:
            record['finished'], record['result'] = now_ms(), {'ok': False, 'error': str(error)}
            self._send('result', key[0], key[2], record['result'])

    # Process cancellation before new calls, expire leases, and retire completed-call history.
    async def run(self):
        try:
            while True:
                # Cancellation is processed before calls, including reordered packets.
                for sub in reversed(self.subscriptions):
                    while sub.items:
                        try:
                            signal = await sub.get(0.01)
                        except asyncio.TimeoutError:
                            break
                        await self._message(signal)
                    if sub.overflow:
                        raise RuntimeError('remote command queue overflow')
                for key, record in tuple(self.records.items()):
                    if record.get('finished') is not None:
                        if elapsed_ms(record['finished']) >= 60000:
                            del self.records[key]
                    elif elapsed_ms(record['renewed']) >= record['lease']:
                        if record.get('task') in self.node.tasks.records:
                            await self.node.tasks.cancel(record['task'])
                await asyncio.sleep(0.01)
        finally:
            for sub in self.subscriptions:
                sub.close()
            self.subscriptions = []

    # Change the epoch so calls negotiated before reset cannot start new service work.
    def invalidate(self):
        # In-flight calls negotiated before a reset cannot start fresh services.
        self.epoch = nonce()

    # Expose retained remote action outcomes and whether each call has finished.
    def snapshot(self):
        return [{'coordinator': key[0], 'correlation': key[2],
                 'state': 'finished' if record.get('finished') is not None else 'running',
                 'result': record.get('result')} for key, record in self.records.items()]
