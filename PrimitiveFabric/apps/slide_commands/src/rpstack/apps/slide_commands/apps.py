"""Signal-driven slide service and one-off client; independent of transport."""
from rpstack.support import asyncio
from rpstack.signals.model import nonce


class SlideCommandApp:
    # Bind a node and slide service, reserving state for incoming commands and replies.
    def __init__(self, node, service='slide'):
        self.node, self.service = node, service
        self.subscription = None
        self.pending = None

    # Confirm the slide exists before subscribing to command signals.
    async def start(self):
        self.node.registry.get(self.service)
        self.subscription = self.node.signals.subscribe('*')

    # Send a response back to the requesting node with the original correlation ID.
    def reply(self, request, name, payload):
        self.node.publish_signal(name, payload, target=request['source'],
                                 correlation=request['correlation'])

    # Validate addressed slide commands, reserve one operation at a time, and schedule
    # correlated replies.
    async def run(self):
        while True:
            request = await self.subscription.get()
            # Commands must explicitly address this node and carry a request ID.
            if request['target'] != self.node.signals.node_id or not request['correlation']:
                continue
            if request['name'] == 'slide.ping':
                self.reply(request, 'slide.ready', {'ready': self.node.accepting and not self.node._claims.get(self.service), 'protocol': 4})
                continue
            if request['name'] not in ('slide.move', 'slide.calibrate', 'slide.observe', 'slide.set_range'):
                continue
            operation = None
            try:
                payload = request['payload']
                if request['name'] == 'slide.set_range':
                    if not isinstance(payload, dict) or set(payload) != {'min_mm', 'max_mm'}:
                        raise ValueError('expected min_mm and max_mm')
                    operation_name, arguments = 'set_range', payload
                elif request['name'] == 'slide.observe':
                    if not isinstance(payload, dict) or payload:
                        raise ValueError('expected empty payload')
                    operation_name, arguments = 'observe_position', {}
                elif request['name'] == 'slide.calibrate':
                    if not isinstance(payload, dict) or set(payload) != {'steps'}:
                        raise ValueError('expected steps')
                    operation_name, arguments = 'calibrate', payload
                else:
                    if not isinstance(payload, dict) or set(payload) != {'position_mm'}:
                        raise ValueError('expected position_mm')
                    value = payload['position_mm']
                    if type(value) not in (int, float):
                        raise ValueError('position_mm must be numeric')
                    operation_name, arguments = 'move_to', {'target': value / 1000.0}
                if self.pending is not None and not self.node.tasks.records[self.pending]['done'].is_set():
                    raise RuntimeError('slide is busy')
                if self.pending is not None:
                    self.node.tasks.records.pop(self.pending, None)
                    self.pending = None
                operation = self.node.submit(self.service, operation_name, arguments)
                # Submission reserves the slide and its transitive dependencies.
                self.pending = self.node.tasks.spawn('slide:reply', self._complete,
                    request, operation, kind='runtime')
            except Exception as error:
                if operation is not None:
                    await self.node.tasks.cancel(operation)
                self.reply(request, 'motion.target.failed', {'error': str(error)})

    # Translate operation progress, results, and failures into response signals for the client.
    async def _complete(self, request, operation):
        try:
            if request['name'] in ('slide.move', 'slide.calibrate'):
                self.reply(request, 'motion.started', dict(request['payload'], operation=request['name']))
            result = await self.node.tasks.wait(operation)
            if request['name'] == 'slide.calibrate':
                self.reply(request, 'slide.calibrated', result)
            elif request['name'] == 'slide.set_range':
                self.reply(request, 'slide.range.updated', result)
            elif request['name'] == 'slide.observe':
                self.reply(request, 'slide.position', result.as_dict())
            else:
                self.reply(request, 'motion.target.reached', result.as_dict())
        except asyncio.CancelledError:
            await self.node.tasks.cancel(operation)
            self.reply(request, 'motion.target.failed', {'error': 'move cancelled'})
            raise
        except Exception as error:
            await self.node.tasks.cancel(operation)
            self.reply(request, 'motion.target.failed', {'error': str(error)})

    # Close the subscription and cancel any outstanding reply task.
    async def stop(self):
        if self.subscription:
            self.subscription.close()
        if self.pending is not None:
            await self.node.tasks.cancel(self.pending)
            self.node.tasks.records.pop(self.pending, None)
            self.pending = None


class MoveOnceApp:
    # Select a one-shot slide command and prepare its expected response and correlation ID.
    def __init__(self, node, target_node='node1', position_mm=100, timeout_s=30,
                 command='move', steps=1000, min_mm=None, max_mm=None):
        if command not in ('move', 'calibrate', 'observe', 'set_range'):
            raise ValueError('unknown slide command')
        self.command, self.steps = command, steps
        self.min_mm, self.max_mm = min_mm, max_mm
        self.completed_signal = {'calibrate': 'slide.calibrated',
                                 'observe': 'slide.position',
                                 'set_range': 'slide.range.updated',
                                 'move': 'motion.target.reached'}[command]
        self.node, self.target_node = node, target_node
        self.position_mm, self.timeout_s = position_mm, timeout_s
        self.correlation = nonce()
        self.subscription = None
        self.received = []
        self.command_sent = False

    # Listen only for replies from the target node matching this command's correlation ID.
    async def start(self):
        self.subscription = self.node.signals.subscribe('*', correlation=self.correlation,
                                                        source=self.target_node)

    # Bound the entire exchange with a timeout and explain whether a command was already sent.
    async def run(self):
        # Retry readiness probes, send the command once, then await its terminal response.
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
                    if signal['payload'].get('protocol', 1) < (4 if self.command == 'set_range' else 3 if self.command == 'observe' else 2):
                        raise RuntimeError('Slide node code is out of date; reinstall the complete slide_nodes package')
                    break
            payload = {'steps': self.steps} if self.command == 'calibrate' else {'position_mm': self.position_mm}
            if self.command == 'set_range':
                payload = {'min_mm': self.min_mm, 'max_mm': self.max_mm}
            if self.command == 'observe':
                payload = {}
            self.node.publish_signal('slide.' + self.command, payload,
                target=self.target_node, correlation=self.correlation)
            self.command_sent = True
            while True:
                signal = await self.subscription.get()
                if signal['name'] not in ('motion.started', self.completed_signal, 'motion.target.failed'):
                    continue
                self.received.append(signal)
                print(signal['name'], signal['payload'])
                if signal['name'] == 'motion.target.failed':
                    raise RuntimeError(signal['payload']['error'])
                if signal['name'] == self.completed_signal:
                    return signal['payload']
        try:
            return await asyncio.wait_for(exchange(), self.timeout_s)
        except asyncio.TimeoutError:
            if self.command_sent and self.command == 'set_range':
                raise RuntimeError('Range update outcome timed out on ' + self.target_node)
            if self.command_sent and self.command == 'observe':
                raise RuntimeError('Position read timed out on ' + self.target_node)
            if self.command_sent:
                raise RuntimeError('Move outcome timed out; motion may still be active on ' + self.target_node)
            raise RuntimeError('No ready reply from ' + self.target_node + '; no move command sent')
        finally:
            self.subscription.close()

    # Release the response subscription when the client is stopped.
    async def stop(self):
        if self.subscription:
            self.subscription.close()
