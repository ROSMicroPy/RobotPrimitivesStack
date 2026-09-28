"""Run a named operation/signal workflow as an Actor's Behavior."""
from somatic_mesh.support import Behavior


class WorkflowBehavior(Behavior):
    def __init__(self, actor, flow):
        super().__init__(actor)
        self.flow = flow
        self.task_id = None

    async def start(self):
        if self.flow not in self.node.document.get('flows', {}):
            raise ValueError('unknown workflow: ' + self.flow)
        if self.node.document['flows'][self.flow].get('autostart', False):
            raise ValueError('actor-owned workflows must not also autostart')

    async def run(self):
        self.task_id = self.node.start_flow(self.flow)
        try:
            return await self.node.tasks.wait(self.task_id)
        finally:
            if self.task_id in self.node.tasks.records:
                await self.node.tasks.cancel(self.task_id)

    async def stop(self):
        if self.task_id in self.node.tasks.records:
            await self.node.tasks.cancel(self.task_id)
