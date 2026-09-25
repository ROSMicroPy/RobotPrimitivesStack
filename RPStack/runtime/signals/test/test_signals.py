import asyncio
import unittest
from rpstack.signals import SignalBus, encode, decode


class Sink:
    # Accept outgoing traffic without delivering it, isolating routing tests from real
    # transports.
    async def send(self, data):
        pass


class SignalTests(unittest.IsolatedAsyncioTestCase):
    # Build a signal bus with mesh and ROS sink ports for route assertions.
    def bus(self, node='a', entity='Robie1', **kwargs):
        bus = SignalBus(entity, node, **kwargs)
        bus.add_transport('mesh', Sink())
        bus.add_transport('ros', Sink())
        return bus

    # Check local, mesh, and ROS delivery for every selected route combination.
    async def test_all_route_combinations(self):
        for bits in range(8):
            routes = [route for bit, route in enumerate(('local', 'mesh', 'ros')) if bits & (1 << bit)]
            bus = self.bus(routes=routes)
            sub = bus.subscribe('go')
            bus.publish('go', {'value': 1})
            self.assertEqual(bool(sub.items), 'local' in routes)
            for route in ('mesh', 'ros'):
                self.assertEqual(bool(bus.ports[route]['queue']), route in routes)

    # Ensure duplicate packets across transports and foreign-entity signals are not delivered
    # twice.
    async def test_cross_transport_duplicates_and_foreign_entities(self):
        sender, receiver = self.bus(), self.bus('b')
        sub = receiver.subscribe('go')
        packet = encode(sender.publish('go'))
        self.assertTrue(receiver.receive(packet, 'mesh'))
        self.assertFalse(receiver.receive(packet, 'ros'))
        self.assertEqual(len(sub.items), 1)
        self.assertFalse(receiver.receive(encode(self.bus(entity='Robie2').publish('go')), 'mesh'))
        self.assertEqual(receiver.stats['foreign'], 1)

    # Verify forwarding decrements hop count and replay detection terminates bridge loops.
    async def test_bridge_and_relay_loops_stop_at_dedup(self):
        a = self.bus(bridges={'mesh': ['ros']})
        b = self.bus('b', bridges={'ros': ['mesh']})
        b.ports['ros']['relay'] = True
        origin = self.bus('origin').publish('go')
        a.receive(encode(origin), 'mesh')
        forwarded = a.ports['ros']['queue'][0][0]
        self.assertEqual(forwarded['hops'], origin['hops'] - 1)
        b.receive(encode(forwarded), 'ros')
        self.assertFalse(a.receive(encode(b.ports['mesh']['queue'][0][0]), 'mesh'))
        self.assertEqual(len(a.ports['ros']['queue']), 1)

    # Check subscriber filters and prevent payload mutation from leaking across delivery copies.
    async def test_target_correlation_source_and_payload_isolation(self):
        bus = self.bus(routes=['local', 'mesh'])
        matching = bus.subscribe('go', correlation='run1', source='a')
        other = bus.subscribe('go', correlation='run2')
        payload = {'values': [1]}
        published = bus.publish('go', payload, correlation='run1', target='a')
        payload['values'].append(2)
        published['payload']['values'].append(3)
        self.assertEqual((await matching.get())['payload'], {'values': [1]})
        self.assertEqual(bus.ports['mesh']['queue'][0][0]['payload'], {'values': [1]})
        self.assertFalse(other.items)
        bus.publish('go', correlation='run1', target='elsewhere')
        self.assertFalse(matching.items)

    # Reject congested publication before partial delivery and refuse exhausted replay tracking.
    async def test_queue_pressure_is_atomic_and_dedup_fails_closed(self):
        bus = self.bus(queue_limit=1, routes=['local','mesh'])
        sub = bus.subscribe('go')
        bus.publish('go')
        with self.assertRaisesRegex(RuntimeError, 'queue full'):
            bus.publish('go')
        self.assertEqual(len(sub.items), 1)
        small = self.bus(seen_limit=1)
        small.publish('go')
        with self.assertRaisesRegex(RuntimeError, 'deduplication'):
            small.receive(encode(self.bus('other').publish('go')), 'mesh')

    # Ensure zero-hop packets are not relayed and expired subscription items are skipped.
    async def test_expired_signals_and_hop_zero(self):
        bus = self.bus(bridges={'mesh':['ros']})
        sub = bus.subscribe('go')
        message = self.bus('b').publish('go', ttl_ms=1, hops=0)
        bus.receive(encode(message), 'mesh')
        self.assertFalse(bus.ports['ros']['queue'])
        await asyncio.sleep(0.005)
        with self.assertRaises(asyncio.TimeoutError):
            await sub.get(0.005)

    # Reject malformed envelopes, excessive payload sizes, and non-finite JSON values.
    def test_malformed_oversized_and_nonfinite_rejected(self):
        bus = self.bus()
        for raw in (b'{}', b'null', b'[]', b'\xff', b'{' * 3000):
            self.assertFalse(bus.receive(raw, 'mesh'))
        with self.assertRaises(ValueError):
            bus.publish('go', float('nan'))
        with self.assertRaises(ValueError):
            bus.publish('go', 'x' * 3000)
        raw = decode(encode(bus.publish('go')))
        raw['version'] = True
        with self.assertRaises(ValueError):
            encode(raw)

    # Exercise bounded per-origin replay tracking under high rates, reordering, duplication, and
    # stale packets.
    def test_replay_window_handles_high_rates_reordering_and_stale_packets(self):
        sender, receiver = self.bus(), self.bus('b')
        packets = [encode(sender.publish('go')) for _ in range(1000)]
        for data in packets[:-2]:
            self.assertTrue(receiver.receive(data, 'mesh'))
        self.assertTrue(receiver.receive(packets[-1], 'mesh'))
        self.assertTrue(receiver.receive(packets[-2], 'mesh'))
        self.assertFalse(receiver.receive(packets[-2], 'mesh'))
        self.assertFalse(receiver.receive(packets[0], 'mesh'))
        self.assertEqual(len(receiver.seen), 1)
