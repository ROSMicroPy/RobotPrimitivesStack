"""ROS-independent slide admission, health, and remote operation lifecycle."""
import asyncio
import math
import time

from rpstack.execution_engine.distributed import RemoteCancelled
from rpstack.signals.model import nonce


def position_sample(value):
    """Validate a linear measurement without inventing timestamps or quality."""
    if not isinstance(value, dict) or value.get('kind') != 'linear' or value.get('unit') != 'm':
        raise ValueError('expected linear position in metres')
    if type(value.get('valid')) is not bool:
        raise ValueError('position validity must be explicit')
    if type(value.get('value')) not in (int, float) or not math.isfinite(value['value']):
        raise ValueError('position must be finite')
    quality = value.get('quality')
    if type(quality) not in (int, float) or not math.isfinite(quality) or not 0 <= quality <= 1:
        raise ValueError('position quality must be between zero and one')
    if value.get('reference_frame') is not None and not isinstance(value['reference_frame'], str):
        raise ValueError('invalid reference frame')
    stamp = value.get('timestamp_ns')
    if stamp is not None and (type(stamp) is not int or not 0 <= stamp < 2 ** 64):
        raise ValueError('invalid source timestamp')
    return dict(value)


class SlideController:
    """One gateway endpoint; the worker remains the authority on resource claims."""
    def __init__(self, node, target_node, service='slide', health_timeout_s=1.0,
                 inventory_interval_s=5.0, move_timeout_s=60.0, cancel_timeout_s=3.0):
        if node.remote is None or target_node not in node.remote.peers:
            raise ValueError('gateway target must be an execution peer')
        for value in (health_timeout_s, inventory_interval_s, move_timeout_s, cancel_timeout_s):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError('gateway timeouts must be positive finite numbers')
        # Each idle refresh retains two remote results for 60 seconds.
        if inventory_interval_s < 3:
            raise ValueError('inventory interval must be at least 3 seconds')
        self.node, self.target, self.service = node, target_node, service
        self.health_timeout = health_timeout_s
        self.inventory_interval = inventory_interval_s
        self.move_timeout, self.cancel_timeout = move_timeout_s, cancel_timeout_s
        self.ready = self.reserved = self.closed = False
        self.fault = ''
        self.uncertain = False
        self.epoch = None
        self.last_seen = self.last_sample = self.last_inventory = 0.0
        self.sample = None
        self.bounds = (None, None)
        self.cancel_event = None
        self.on_sample = lambda sample: None

    def reserve(self, target):
        """Synchronously gate concurrent goals before the action execute callback runs."""
        fresh = time.monotonic() - self.last_seen <= self.health_timeout * 2
        measured = self.sample is not None and self.sample['valid']
        if (not self.node.accepting or self.closed or self.reserved or self.uncertain or not self.ready or not fresh or
                not measured or time.monotonic() - self.last_sample > self.inventory_interval * 2):
            return False
        if type(target) not in (int, float) or not math.isfinite(target):
            return False
        low, high = self.bounds
        if (low is not None and target < low) or (high is not None and target > high):
            return False
        self.reserved = True
        return True

    def receive_sample(self, payload):
        sample = position_sample(payload)
        self.sample, self.last_sample = sample, time.monotonic()
        self.on_sample(sample)

    def fail(self, message):
        self.ready = False
        self.fault = str(message)
        if self.reserved:
            self.uncertain = True
            if self.cancel_event is not None:
                self.cancel_event.set()

    async def refresh(self):
        """Probe admission continuously; read hardware only when no goal is reserved."""
        if not self.node.accepting:
            self.fail('gateway node stopped')
            return
        try:
            epoch = await self.node.remote.probe(self.target, self.health_timeout)
            if self.epoch is not None and self.epoch != epoch:
                self.fail('worker restarted or reset')
                self.sample = None
                self.last_inventory = 0
            self.epoch, self.last_seen = epoch, time.monotonic()
            if self.reserved or self.uncertain or self.closed:
                return
            if self.last_inventory and time.monotonic() - self.last_inventory < self.inventory_interval:
                return
            # Do not advertise admission while awaiting reads: a new goal would
            # otherwise race the observation's managed resource claim.
            self.ready = False
            self.last_inventory = time.monotonic()
            status = await self.node.remote.invoke(self.target, self.service, 'status', {},
                                                   nonce(), self.health_timeout)
            if not isinstance(status, dict) or not status.get('active') or not status.get('calibrated'):
                self.fault = 'slide inactive or calibration required'
                return
            limits = status.get('range_mm', {})
            bounds = tuple(limits.get(key) for key in ('min_mm', 'max_mm'))
            if any(v is not None and (type(v) not in (int, float) or not math.isfinite(v)) for v in bounds):
                raise ValueError('invalid worker travel range')
            self.bounds = tuple(v / 1000 if v is not None else None for v in bounds)
            sample = await self.node.remote.invoke(self.target, self.service, 'observe_position', {},
                                                   nonce(), self.health_timeout)
            self.receive_sample(sample)
            self.ready = self.sample['valid']
            self.fault = '' if self.ready else 'invalid position measurement'
        except Exception as error:
            self.fail('worker unavailable: ' + (str(error) or type(error).__name__))

    async def move(self, target, cancel_event):
        if not self.reserved:
            raise RuntimeError('goal was not reserved')
        self.cancel_event = cancel_event
        try:
            if not self.node.accepting or self.closed or self.uncertain:
                raise RuntimeError('gateway stopped or worker state unconfirmed')
            result = await self.node.remote.invoke(self.target, self.service, 'move_to',
                {'target': target}, nonce(), self.move_timeout, cancel_event=cancel_event,
                cancel_timeout_s=self.cancel_timeout)
            self.receive_sample(result)
            if not self.sample['valid']:
                raise ValueError('worker returned an invalid final measurement')
            if self.uncertain:
                return {'state': 'aborted', 'message': self.fault, 'confirmed': False}
            return {'state': 'succeeded', 'message': 'target reached', 'confirmed': True}
        except RemoteCancelled as error:
            if self.uncertain:
                return {'state': 'aborted', 'message': self.fault, 'confirmed': False}
            if cancel_event.is_set():
                return {'state': 'cancelled', 'message': str(error), 'confirmed': True}
            self.fail('worker cancelled operation or lease expired')
            return {'state': 'aborted', 'message': self.fault, 'confirmed': True}
        except asyncio.CancelledError:
            self.fail('gateway stopped; remote outcome unconfirmed')
            raise
        except Exception as error:
            self.fail('move failed; verify worker state: ' + (str(error) or type(error).__name__))
            return {'state': 'aborted', 'message': self.fault, 'confirmed': False}
        finally:
            self.reserved = self.ready = False
            self.cancel_event = None
            self.last_inventory = 0

    def diagnostic(self):
        if self.closed or not self.node.accepting:
            return 2, 'gateway stopped'
        if self.uncertain:
            return 2, self.fault + '; restart gateway after checking device'
        if not self.last_seen or time.monotonic() - self.last_seen > self.health_timeout * 2:
            return 3, self.fault or 'worker not observed'
        if self.fault:
            return 1, self.fault
        return 0, 'moving' if self.reserved else 'ready' if self.ready else 'checking readiness'
