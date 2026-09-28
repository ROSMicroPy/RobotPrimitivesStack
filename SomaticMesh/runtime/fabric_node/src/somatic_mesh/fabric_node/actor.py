"""A named participant that owns a Behavior and its managed execution."""
from somatic_mesh.support import call


class Actor:
    """Bind identity and configuration to one Behavior on a FabricNode.

    Actor IDs are node-local. The task ID identifies one execution, while the
    Actor ID identifies the configured participant for its deployment lifetime.
    """
    def __init__(self, node, actor_id, factory, behavior_name, config=None,
                 mode='resident', version=None):
        self.node = node
        self.id = actor_id
        self.behavior_name = behavior_name
        self.version = version
        self.config = dict(config or {})
        self.mode = mode
        self.behavior = None
        self.task_id = None
        self._factory = factory
        self._state = 'created'
        self._stopped = False

    @property
    def address(self):
        return (self.node.signals.entity, self.node.signals.node_id, self.id)

    @property
    def state(self):
        if self._state == 'running' and self.task_id in self.node.tasks.records:
            return self.node.tasks.records[self.task_id]['state']
        return self._state

    async def start(self):
        if self._state != 'created':
            raise RuntimeError('actor already started: ' + self.id)
        self._state = 'starting'
        try:
            self.behavior = self._factory(self, **self.config)
            await call(self.behavior.start)
            self.task_id = self.node.tasks.spawn('actor:' + self.id,
                self.behavior.run, kind='actor', owner=self.id)
            self._state = 'running'
        except BaseException:
            self._state = 'failed'
            raise
        return self.task_id

    async def wait(self):
        if self.task_id is None:
            raise RuntimeError('actor has not started: ' + self.id)
        return await self.node.tasks.wait(self.task_id)

    async def stop(self):
        if self._stopped:
            return
        self._stopped = True
        try:
            if self.task_id in self.node.tasks.records:
                await self.node.tasks.cancel(self.task_id)
            if self.behavior is not None:
                await call(self.behavior.stop)
        finally:
            self._state = 'stopped'

    def describe(self):
        """Public identity and execution state; never include configuration."""
        return {'id': self.id, 'behavior': self.behavior_name,
                'version': self.version, 'mode': self.mode,
                'state': self.state, 'task_id': self.task_id}
