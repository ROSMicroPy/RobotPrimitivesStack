"""Host-only simulated motor/TOF pair, using the real composite slide service."""
from rpstack.motor_control.motor_drivers.step_dir import StepDirDriver


class Carriage:
    position_mm = 0
    stalled = False


class Pin:
    def __init__(self, number):
        self.state = 0

    def value(self, value):
        self.state = value


class MotorDriver(StepDirDriver):
    def initialize(self, **kwargs):
        kwargs['pin_factory'] = Pin
        kwargs['step_delay_us'] = 1
        return super().initialize(**kwargs)

    async def move_steps(self, steps, direction=True):
        result = await super().move_steps(steps, direction)
        if not Carriage.stalled:
            Carriage.position_mm += steps if direction else -steps
        return result

    def move_steps_blocking(self, steps, direction=True, cancelled=None):
        before = self.position_steps
        try:
            return super().move_steps_blocking(steps, direction, cancelled)
        finally:
            if not Carriage.stalled:
                Carriage.position_mm += self.position_steps - before


class DistanceDriver:
    def initialize(self, **kwargs):
        return True

    def read_distance_mm(self):
        return Carriage.position_mm

    def set_active(self, active):
        return True

    def shutdown(self):
        return True


def simulated_node(document, calibrate=False):
    from rpstack.node_runtime import NodeRuntime
    for component, implementation, cls in (
        ('motor_control', 'step_dir', 'MotorDriver'),
        ('distance_sensor', 'vl53l4cd', 'DistanceDriver'),
    ):
        document['components'][component]['service']['implementations'][implementation]['entry_point'] = __name__ + ':' + cls
    class SimulatedRuntime(NodeRuntime):
        async def boot(self):
            await super().boot()
            if calibrate:
                await self.invoke('slide', 'calibrate', {'steps': 1000})
            return self
    return SimulatedRuntime(document, {'i2c': lambda spec: object()})
