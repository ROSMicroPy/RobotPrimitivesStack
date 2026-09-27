"""Bounded ESP-NOW signal transport with fragment reassembly."""
from rpstack.support import asyncio, now_ms, elapsed_ms


class Framing:
    MAGIC = b'\x7fM'
    HEADER = 7

    # Validate packet limits and prepare bounded fragment assembly state.
    def __init__(self, frame_bytes=240, max_bytes=2048, max_pending=8, timeout_ms=3000):
        if not 8 <= frame_bytes <= 250 or not 1 <= max_bytes <= 65535 or max_pending < 1 or timeout_ms < 1:
            raise ValueError('invalid fragmentation limits')
        self.frame_bytes, self.max_bytes = frame_bytes, max_bytes
        self.max_pending, self.timeout_ms = max_pending, timeout_ms
        self.pending = {}
        self.sequence = 0

    # Pass through small payloads or split messages into sequence-tagged radio frames.
    def split(self, data):
        data = bytes(data)
        if not data or len(data) > self.max_bytes:
            raise ValueError('invalid message size')
        if len(data) <= self.frame_bytes and not data.startswith(self.MAGIC):
            return [data]
        size = self.frame_bytes - self.HEADER
        count = (len(data) + size - 1) // size
        if count > 255:
            raise ValueError('too many fragments')
        self.sequence = (self.sequence + 1) % 65536
        header = self.MAGIC + bytes((1, self.sequence >> 8, self.sequence & 255, count))
        return [header + bytes((i,)) + data[i * size:(i + 1) * size] for i in range(count)]

    # Discard fragment assemblies that have exceeded their completion deadline.
    def expire(self):
        for key, value in tuple(self.pending.items()):
            if elapsed_ms(value['started']) >= self.timeout_ms:
                del self.pending[key]

    # Validate and collect peer fragments, returning a message only when assembly is complete.
    def join(self, peer, frame):
        self.expire()
        peer, frame = bytes(peer), bytes(frame)  # ESP-NOW reuses receive buffers.
        if not frame or len(frame) > self.frame_bytes:
            return None
        if not frame.startswith(self.MAGIC):
            return frame if len(frame) <= self.max_bytes else None
        if len(frame) <= self.HEADER or frame[2] != 1:
            return None
        count, index = frame[5], frame[6]
        size = self.frame_bytes - self.HEADER
        if not count or index >= count or (count - 1) * size >= self.max_bytes:
            return None
        payload = frame[self.HEADER:]
        if index < count - 1 and len(payload) != size:
            return None
        key = (peer, frame[3:5])
        item = self.pending.get(key)
        if item is None:
            if len(self.pending) >= self.max_pending:
                return None
            item = {'started': now_ms(), 'count': count, 'parts': {}, 'size': 0}
            self.pending[key] = item
        if item['count'] != count or (index in item['parts'] and item['parts'][index] != payload):
            del self.pending[key]
            return None
        if index not in item['parts']:
            item['parts'][index] = payload
            item['size'] += len(payload)
        if item['size'] > self.max_bytes:
            del self.pending[key]
            return None
        if len(item['parts']) == count:
            del self.pending[key]
            return b''.join(item['parts'][i] for i in range(count))
        return None


class EspNowTransport:
    # Prepare fragmentation and polling settings for an ESP-NOW broadcast transport.
    def __init__(self, entity, node_id, channel=None, poll_ms=10, max_bytes=2048,
                 max_pending=8, timeout_ms=3000, radio=None):
        if poll_ms < 1:
            raise ValueError('poll_ms must be positive')
        self.channel, self.poll_ms = channel, poll_ms
        self.framing = Framing(max_bytes=max_bytes, max_pending=max_pending, timeout_ms=timeout_ms)
        self.radio = radio
        self.peer = b'\xff' * 6

    # Activate the radio, enforce the Wi-Fi channel constraint, and register the broadcast peer.
    async def start(self):
        if self.radio is None:
            import network
            import espnow
            nic = network.WLAN(network.STA_IF)
            nic.active(True)
            if self.channel is not None:
                if nic.isconnected() and nic.config('channel') != self.channel:
                    raise ValueError('ESP-NOW channel must match connected Wi-Fi')
                nic.config(channel=self.channel)
            self.radio = espnow.ESPNow()
        self.radio.active(True)
        self.radio.add_peer(self.peer)

    # Queue each fragment for broadcast, yielding between frames without waiting for
    # acknowledgements.
    async def send(self, data):
        for frame in self.framing.split(data):
            # sync=False only queues a frame; never wait for radio acknowledgements.
            self.radio.send(self.peer, frame, False)
            await asyncio.sleep(self.poll_ms / 1000)

    # Poll radio frames and return the next complete message while expiring stale assemblies.
    async def recv(self):
        while True:
            peer, frame = self.radio.irecv(0)
            if peer is not None:
                data = self.framing.join(peer, frame)
                if data is not None:
                    return data
            else:
                self.framing.expire()
            await asyncio.sleep(self.poll_ms / 1000)

    # Deactivate the radio and discard unfinished fragment assemblies.
    async def stop(self):
        if self.radio is not None:
            self.radio.active(False)
        self.framing.pending.clear()
