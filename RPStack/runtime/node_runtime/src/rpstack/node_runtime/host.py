"""Host independent logical nodes on one device/event loop."""
from rpstack.support import asyncio
from .node import NodeRuntime
from .manifest import ManifestError


class NodeHost:
    # Collect nodes under one host, rejecting duplicate entity/node identities.
    def __init__(self, nodes):
        self.nodes = list(nodes)
        identities = [(node.signals.entity, node.signals.node_id) for node in self.nodes]
        if len(set(identities)) != len(identities):
            raise ManifestError('host nodes require unique entity/node identities')
        self._booted = []
        self.failures = {}

    # Load each manifest into a node runtime before assembling the host.
    @classmethod
    def load(cls, paths):
        return cls([NodeRuntime.load(path) for path in paths])

    # Boot nodes in supplied order and unwind already-started nodes if startup fails.
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

    # Shut down booted nodes in reverse order and aggregate cleanup errors.
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

    # Boot the host, supervise node lifetimes concurrently, and always clean up on exit.
    async def run(self):
        # Wait for one node, record its failure, and shut it down when its lifetime ends.
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


# Run a group of manifest-defined nodes on a shared event loop.
def run_manifests(paths):
    asyncio.run(NodeHost.load(paths).run())
