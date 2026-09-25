"""Bounded signal link between logical nodes in one Python interpreter."""
from rpstack.support import asyncio


class InProcessTransport:
    _segments = {}

    # Prepare a bounded mailbox on an entity-scoped in-process link segment.
    def __init__(self, entity, node_id, segment='default', capacity=16):
        if type(capacity) is not int or capacity < 1:
            raise ValueError('capacity must be positive')
        self.key = (entity, segment)
        self.node_id = node_id
        self.capacity = capacity
        self.items = []
        self.ready = asyncio.Event()
        self.active = False
        self.dropped = 0

    # Join the link segment while rejecting duplicate node identities.
    async def start(self):
        if self.active:
            return
        peers = self._segments.setdefault(self.key, [])
        if any(peer.node_id == self.node_id for peer in peers):
            raise ValueError('duplicate node identity on in-process link')
        peers.append(self)
        self.active = True

    # Copy bytes to other local peers, counting drops when their mailboxes are full.
    async def send(self, data):
        if not self.active:
            raise RuntimeError('transport is stopped')
        for peer in self._segments.get(self.key, []):
            if peer is self:
                continue
            if len(peer.items) >= peer.capacity:
                peer.dropped += 1
                continue
            peer.items.append(bytes(data))
            peer.ready.set()
        await asyncio.sleep(0)

    # Wait for and consume the oldest available local message.
    async def recv(self):
        while not self.items:
            await self.ready.wait()
        data = self.items.pop(0)
        if not self.items:
            self.ready.clear()
        return data

    # Leave the shared segment and clear this transport's pending messages.
    async def stop(self):
        peers = self._segments.get(self.key, [])
        if self in peers:
            peers.remove(self)
        if not peers:
            self._segments.pop(self.key, None)
        self.active = False
        self.items.clear()
        self.ready.clear()
