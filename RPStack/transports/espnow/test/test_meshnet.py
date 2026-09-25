import asyncio
import unittest
from rpstack.espnow import Framing, EspNowTransport


class MeshTests(unittest.IsolatedAsyncioTestCase):
    # Check fragment reordering and duplication without mixing assemblies from different peers.
    def test_out_of_order_duplicates_and_peer_isolation(self):
        codec = Framing()
        payload = b'abcd' * 400
        frames = codec.split(payload)
        receiver = Framing()
        self.assertIsNone(receiver.join(b'peer-a', frames[-1]))
        self.assertIsNone(receiver.join(b'peer-a', frames[-1]))
        self.assertIsNone(receiver.join(b'peer-b', frames[0]))
        result = None
        for frame in frames[:-1]:
            result = receiver.join(b'peer-a', frame)
        self.assertEqual(result, payload)
        self.assertEqual(len(receiver.pending), 1)

    # Verify fragment assembly capacity and expiration even without incoming packets.
    async def test_bounded_buffers_expire_without_traffic(self):
        receiver = Framing(max_pending=2, timeout_ms=1)
        for index in range(10):
            self.assertIsNone(receiver.join(bytes([index]), receiver.split(b'x' * 500)[0]))
        self.assertEqual(len(receiver.pending), 2)
        await asyncio.sleep(0.005)
        receiver.expire()
        self.assertFalse(receiver.pending)

    # Reject invalid framing and discard an assembly containing conflicting duplicate fragments.
    def test_malformed_fragments_and_conflicts(self):
        codec = Framing()
        for raw in (b'\x7fM', b'\x7fM\x02\x00\x00\x01\x00x', b'\x7fM\x01\x00\x00\xff\x00x', b'x'*251):
            self.assertIsNone(codec.join(b'peer', raw))
        first = codec.split(b'x' * 500)[0]
        codec.join(b'peer', first)
        codec.join(b'peer', first[:-1] + b'y')
        self.assertFalse(codec.pending)

    # Exercise fragmentation with mutable radio buffers and confirm nonblocking send/receive
    # calls.
    async def test_transport_copies_radio_buffers_and_uses_nonblocking_io(self):
        class Radio:
            # Prepare captured outgoing frames and a fake incoming queue.
            def __init__(self): self.queue, self.sent = [], []
            # Accept radio activation without needing physical hardware.
            def active(self, state): pass
            # Accept broadcast-peer registration in the test radio.
            def add_peer(self, peer): pass
            # Capture outgoing frames and the requested acknowledgement mode.
            def send(self, peer, data, sync):
                self.assert_sync = sync
                self.sent.append(data)
            # Assert zero-timeout polling and return the next queued fake frame.
            def irecv(self, timeout):
                assert timeout == 0
                return self.queue.pop(0) if self.queue else (None, None)
        radio = Radio()
        transport = EspNowTransport('Robie1','arm', radio=radio, poll_ms=1)
        await transport.start()
        payload = b'x' * 800
        await transport.send(payload)
        self.assertFalse(radio.assert_sync)
        radio.queue = [(bytearray(b'peer'), bytearray(frame)) for frame in radio.sent]
        self.assertEqual(await transport.recv(), payload)
        await transport.stop()
