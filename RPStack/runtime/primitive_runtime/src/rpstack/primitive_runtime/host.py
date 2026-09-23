"""Host independent logical nodes on one device/event loop."""
from rpstack.execution_engine import asyncio
from .node import NodeRuntime
from .manifest import ManifestError


class NodeHost:
    def __init__(self, nodes):
        self.nodes = list(nodes)
        identities = [(node.signals.entity, node.signals.node_id) for node in self.nodes]
        if len(set(identities)) != len(identities):
            raise ManifestError('host nodes require unique entity/node identities')
        self._booted = []
        self.failures = {}

    @classmethod
    def load(cls, paths):
        return cls([NodeRuntime.load(path) for path in paths])

    async def boot(self):
        if self._booted:
            raise RuntimeError('host already booted')
        try:
            # Put providers before clients. Each app subscribes in start().
            for node in self.nodes:
                self._booted.append(node)
                await node.boot()
        except BaseException:
            await self.shutdown()
            raise
        return self

    async def shutdown(self):
        errors = []
        for node in reversed(self._booted):
            try:
                await node.shutdown()
            except Exception as error:
                errors.append(str(error))
        self._booted = []
        if errors:
            raise RuntimeError('; '.join(errors))

    async def run(self):
        async def serve(node):
            try:
                await node.wait()
            except Exception as error:
                self.failures[(node.signals.entity, node.signals.node_id)] = str(error)
            finally:
                await node.shutdown()
        tasks = []
        try:
            await self.boot()
            tasks = [asyncio.create_task(serve(node)) for node in self.nodes]
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            await self.shutdown()


def run_manifests(paths):
    asyncio.run(NodeHost.load(paths).run())
