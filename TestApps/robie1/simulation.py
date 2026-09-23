"""Host-only simulated devices and lossy links for the Robie1 example/tests."""
import asyncio
from rpstack.signals import decode


class MemoryTransport:
    links = {}

    def __init__(self, entity, node_id, segment='mesh', duplicate=False):
        self.entity, self.node_id, self.segment = entity, node_id, segment
        self.duplicate = duplicate
        self.queue = asyncio.Queue(maxsize=128)
        self.sent = []
        self.drop = set()

    async def start(self):
        self.links.setdefault(self.segment, []).append(self)

    async def send(self, data):
        signal = decode(data)
        self.sent.append(signal)
        del self.sent[:-128]
        if signal['name'] in self.drop or '*' in self.drop:
            return
        for peer in self.links.get(self.segment, []):
            for _ in range(2 if self.duplicate else 1):
                try:
                    peer.queue.put_nowait(bytes(data))
                except asyncio.QueueFull:
                    pass
        await asyncio.sleep(0)

    async def recv(self):
        return await self.queue.get()

    async def stop(self):
        peers = self.links.get(self.segment, [])
        if self in peers:
            peers.remove(self)
        if not peers:
            self.links.pop(self.segment, None)


class SimulatedJoint:
    def __init__(self, signals=None):
        self.signals = signals
        self.position, self.calls, self.moving, self.cancelled = 0, 0, False, False

    async def move(self, position, duration_s=0.02):
        self.calls += 1
        self.moving = True
        try:
            await asyncio.sleep(duration_s)
            self.position = position
            if self.signals:
                self.signals.publish('joint.moved', {'position': position})
            return {'position': self.position}
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        finally:
            self.moving = False

    def status(self):
        return {'position': self.position, 'moving': self.moving}
