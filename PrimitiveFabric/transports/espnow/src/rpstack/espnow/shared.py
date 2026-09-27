"""One ESP-NOW radio per interpreter, shared by independent logical nodes.

Every send reaches local peers and the radio. Applications and manifests do
not change when peers move onto another device. Use one asyncio loop only.
"""
from rpstack.support import asyncio
from . import EspNowTransport


class _RadioHub:
    # Own one physical radio and synchronization state shared by logical node transports.
    def __init__(self, options):
        self.options = options
        self.transport = EspNowTransport('', '', **options)
        self.peers = []
        self.sender = asyncio.Lock()
        self.reader = None
        self.error = None

    # Copy incoming data into bounded peer mailboxes, excluding the sender when supplied.
    def deliver(self, data, source=None):
        for peer in self.peers:
            if peer is source:
                continue
            if len(peer.items) >= peer.capacity:
                peer.dropped += 1
            else:
                peer.items.append(bytes(data))
                peer.ready.set()

    # Distribute radio messages and wake all peers if the shared reader fails.
    async def receive(self):
        try:
            while True:
                self.deliver(await self.transport.recv())
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.error = str(error) or type(error).__name__
            for peer in self.peers:
                peer.ready.set()


class SharedEspNowTransport:
    _hub = None
    _guard = None

    # Prepare a logical node's bounded mailbox and desired shared-radio settings.
    def __init__(self, entity, node_id, channel=6, poll_ms=10, max_bytes=2048,
                 max_pending=8, timeout_ms=3000, capacity=16):
        if type(capacity) is not int or capacity < 1:
            raise ValueError('capacity must be positive')
        self.identity = (entity, node_id)
        self.options = dict(channel=channel, poll_ms=poll_ms, max_bytes=max_bytes,
                            max_pending=max_pending, timeout_ms=timeout_ms)
        self.capacity = capacity
        self.items = []
        self.ready = asyncio.Event()
        self.dropped = 0
        self.hub = None

    # Join or create the shared radio hub after checking options and node identity.
    async def start(self):
        cls = type(self)
        if cls._guard is None:
            cls._guard = asyncio.Lock()
        async with cls._guard:
            if self.hub is not None:
                return
            hub = cls._hub
            if hub is None:
                hub = _RadioHub(self.options)
                try:
                    await hub.transport.start()
                except BaseException:
                    await hub.transport.stop()
                    raise
                hub.reader = asyncio.create_task(hub.receive())
                cls._hub = hub
            elif hub.options != self.options:
                raise ValueError('local nodes must share ESP-NOW channel and radio options')
            if hub.error:
                raise RuntimeError(hub.error)
            if any(peer.identity == self.identity for peer in hub.peers):
                raise ValueError('duplicate local entity/node identity')
            hub.peers.append(self)
            self.hub = hub

    # Deliver to local peers, then serialize radio transmission so fragments cannot interleave.
    async def send(self, data):
        hub = self.hub
        if hub is None:
            raise RuntimeError('transport is stopped')
        if hub.error:
            raise RuntimeError(hub.error)
        hub.deliver(data, source=self)
        # Serialize fragments from different logical nodes on the same radio.
        async with hub.sender:
            await hub.transport.send(data)

    # Wait for mailbox data while surfacing shared-radio failure or shutdown.
    async def recv(self):
        while True:
            hub = self.hub
            if hub is None:
                raise RuntimeError('transport is stopped')
            if hub.error:
                raise RuntimeError(hub.error)
            if self.items:
                data = self.items.pop(0)
                if not self.items:
                    self.ready.clear()
                return data
            await self.ready.wait()

    # Detach this node and shut down the physical radio when its last peer leaves.
    async def stop(self):
        cls = type(self)
        if cls._guard is None:
            return
        async with cls._guard:
            hub = self.hub
            if hub is None:
                return
            hub.peers.remove(self)
            self.hub = None
            self.items.clear()
            self.ready.set()
            if not hub.peers:
                hub.reader.cancel()
                try:
                    await hub.reader
                except asyncio.CancelledError:
                    pass
                try:
                    await hub.transport.stop()
                finally:
                    cls._hub = None
