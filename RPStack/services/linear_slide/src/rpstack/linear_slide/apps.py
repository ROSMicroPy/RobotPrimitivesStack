"""Signal-driven slide service and one-off client; independent of transport."""
from rpstack.execution_engine import asyncio
from rpstack.signals.model import nonce


class SlideCommandApp:
    def __init__(self, node, service='slide'):
        self.node, self.service = node, service
        self.subscription = None
        self.pending = None

    async def start(self):
        self.node.registry.get(self.service)
        self.subscription = self.node.signals.subscribe('*')

    def reply(self, request, name, payload):
        self.node.publish_signal(name, payload, target=request['source'],
                                 correlation=request['correlation'])

    async def run(self):
        while True:
            request = await self.subscription.get()
            # Commands must explicitly address this node and carry a request ID.
            if request['target'] != self.node.signals.node_id or not request['correlation']:
                continue
            if request['name'] == 'slide.ping':
                self.reply(request, 'slide.ready', {'ready': self.node.accepting})
                continue
            if request['name'] != 'slide.move':
                continue
            operation = None
            try:
                payload = request['payload']
                if not isinstance(payload, dict) or set(payload) != {'position_mm'}:
                    raise ValueError('expected position_mm')
                value = payload['position_mm']
                if type(value) not in (int, float):
                    raise ValueError('position_mm must be numeric')
                if self.pending is not None and not self.node.tasks.records[self.pending]['done'].is_set():
                    raise RuntimeError('slide is busy')
                if self.pending is not None:
                    self.node.tasks.records.pop(self.pending, None)
                    self.pending = None
                operation = self.node.submit(self.service, 'move_to', {'target': value / 1000.0})
                # Submission reserves the slide and its transitive dependencies.
                self.pending = self.node.tasks.spawn('slide:reply', self._complete,
                    request, operation, kind='runtime')
            except Exception as error:
                if operation is not None:
                    await self.node.tasks.cancel(operation)
                self.reply(request, 'motion.target.failed', {'error': str(error)})

    async def _complete(self, request, operation):
        try:
            self.reply(request, 'motion.started', {'position_mm': request['payload']['position_mm']})
            result = await self.node.tasks.wait(operation)
            self.reply(request, 'motion.target.reached', result.as_dict())
        except asyncio.CancelledError:
            await self.node.tasks.cancel(operation)
            self.reply(request, 'motion.target.failed', {'error': 'move cancelled'})
            raise
        except Exception as error:
            await self.node.tasks.cancel(operation)
            self.reply(request, 'motion.target.failed', {'error': str(error)})

    async def stop(self):
        if self.subscription:
            self.subscription.close()
        if self.pending is not None:
            await self.node.tasks.cancel(self.pending)
            self.node.tasks.records.pop(self.pending, None)
            self.pending = None


class MoveOnceApp:
    def __init__(self, node, target_node='node1', position_mm=100, timeout_s=30):
        self.node, self.target_node = node, target_node
        self.position_mm, self.timeout_s = position_mm, timeout_s
        self.correlation = nonce()
        self.subscription = None
        self.received = []
        self.command_sent = False

    async def start(self):
        self.subscription = self.node.signals.subscribe('*', correlation=self.correlation,
                                                        source=self.target_node)

    async def run(self):
        async def exchange():
            # A lost readiness probe is safe to retry. Never retry a move.
            while True:
                self.node.publish_signal('slide.ping', target=self.target_node,
                                         correlation=self.correlation)
                try:
                    signal = await self.subscription.get(0.25)
                except asyncio.TimeoutError:
                    continue
                if signal['name'] == 'slide.ready' and signal['payload'].get('ready'):
                    break
            self.node.publish_signal('slide.move', {'position_mm': self.position_mm},
                target=self.target_node, correlation=self.correlation)
            self.command_sent = True
            while True:
                signal = await self.subscription.get()
                if signal['name'] not in ('motion.started', 'motion.target.reached', 'motion.target.failed'):
                    continue
                self.received.append(signal)
                print(signal['name'], signal['payload'])
                if signal['name'] == 'motion.target.failed':
                    raise RuntimeError(signal['payload']['error'])
                if signal['name'] == 'motion.target.reached':
                    return signal['payload']
        try:
            return await asyncio.wait_for(exchange(), self.timeout_s)
        except asyncio.TimeoutError:
            if self.command_sent:
                raise RuntimeError('Move outcome timed out; motion may still be active on ' + self.target_node)
            raise RuntimeError('No ready reply from ' + self.target_node + '; no move command sent')
        finally:
            self.subscription.close()

    async def stop(self):
        if self.subscription:
            self.subscription.close()
