"""Actor identity, Behavior ownership, rollback, and workflow cleanup."""
import asyncio
import sys
import unittest
from pathlib import Path

for source in Path(__file__).resolve().parents[3].glob('*/*/src'):
    sys.path.insert(0, str(source))

from somatic_mesh.support import Behavior
from somatic_mesh.fabric_node import Actor, FabricNode, ManifestError


class ProbeBehavior(Behavior):
    stopped = []

    def __init__(self, actor, fail_start=False, value=42, secret=None):
        super().__init__(actor)
        self.fail_start, self.value = fail_start, value

    async def start(self):
        if self.fail_start:
            raise RuntimeError('preparation failed')

    async def run(self):
        return self.value

    async def stop(self):
        self.stopped.append(self.actor.id)


def document(actors, flows=None):
    return {'manifest': 'somatic.node/v1', 'name': 'test',
            'identity': {'entity': 'lab', 'node': 'host'},
            'components': {}, 'services': {}, 'actors': actors,
            'flows': flows or {}}


def spec(actor_id, **kwargs):
    return dict(id=actor_id, behavior=__name__ + ':ProbeBehavior',
                version='1.2.0', mode='oneshot', **kwargs)


class ActorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        ProbeBehavior.stopped = []
        self.node = None

    async def asyncTearDown(self):
        if self.node:
            await self.node.shutdown()

    async def test_identity_behavior_and_execution_are_separate(self):
        self.node = FabricNode(document([spec('observe'), spec('report', config={'value': 7})]))
        await self.node.boot()
        first, second = self.node.actors['observe'], self.node.actors['report']
        self.assertIsInstance(first, Actor)
        self.assertIs(first.behavior.actor, first)
        self.assertIs(first.behavior.node, self.node)
        self.assertIsNot(first.behavior, second.behavior)
        self.assertEqual(first.address, ('lab', 'host', 'observe'))
        self.assertEqual(await first.wait(), 42)
        self.assertEqual(await second.wait(), 7)
        self.assertNotEqual(first.task_id, second.task_id)
        self.assertEqual(self.node.tasks.describe(first.task_id)['kind'], 'actor')
        self.assertEqual(first.describe()['state'], 'succeeded')
        await self.node.wait()
        with self.assertRaisesRegex(RuntimeError, 'already started'):
            await first.start()

    async def test_discovery_has_assignment_without_private_configuration(self):
        self.node = FabricNode(document([spec('observe', config={'secret': 'do-not-publish'})]))
        await self.node.boot()
        public = self.node.discovery()['actors'][0]
        self.assertEqual(public['behavior'], __name__ + ':ProbeBehavior')
        self.assertEqual(public['version'], '1.2.0')
        self.assertNotIn('do-not-publish', str(self.node.discovery()))
        self.assertNotIn('do-not-publish', str(self.node.execution_status()))

    async def test_partial_startup_unwinds_behaviors_once_in_reverse_order(self):
        self.node = FabricNode(document([spec('first'), spec('second', config={'fail_start': True})]))
        with self.assertRaisesRegex(RuntimeError, 'preparation failed'):
            await self.node.boot()
        self.assertEqual(ProbeBehavior.stopped, ['second', 'first'])
        self.assertFalse(self.node.tasks.snapshot())
        await self.node.shutdown()
        self.assertEqual(ProbeBehavior.stopped, ['second', 'first'])

    async def test_invalid_actor_declarations_are_rejected_before_boot(self):
        invalid = [dict(id='x'), dict(spec('x'), behavior=3),
                   dict(spec('x'), version=''), dict(spec('x'), config=[]),
                   dict(spec('x'), requires=['unknown']), dict(spec('x'), mode='invalid')]
        for actor in invalid:
            with self.subTest(actor=actor), self.assertRaises(ManifestError):
                FabricNode(document([actor]))
        with self.assertRaises(ManifestError):
            FabricNode(document([spec('x'), spec('x')]))

    async def test_workflow_cancellation_releases_wait(self):
        actor = {'id': 'sequence', 'behavior': 'somatic_mesh.execution_engine:WorkflowBehavior',
                 'mode': 'oneshot', 'config': {'flow': 'sequence'}}
        self.node = FabricNode(document([actor], {'sequence': {'start': 'wait',
            'nodes': {'wait': {'wait_for': 'operator.ready', 'timeout_s': 5}}}}))
        await self.node.boot()
        instance = self.node.actors['sequence']
        await asyncio.sleep(.01)
        self.assertIsNotNone(instance.behavior.task_id)
        await instance.stop()
        self.assertEqual(self.node.tasks.describe(instance.behavior.task_id)['state'], 'cancelled')
        self.assertEqual(instance.state, 'stopped')

    async def test_workflow_completion_is_an_actor_result(self):
        actor = {'id': 'sequence', 'behavior': 'somatic_mesh.execution_engine:WorkflowBehavior',
                 'mode': 'oneshot', 'config': {'flow': 'sequence'}}
        self.node = FabricNode(document([actor], {'sequence': {'start': 'emit',
            'nodes': {'emit': {'emit': 'sequence.ready'}}}}))
        await self.node.boot()
        await asyncio.wait_for(self.node.wait(), 1)
        instance = self.node.actors['sequence']
        self.assertEqual(instance.state, 'succeeded')
        self.assertEqual(self.node.tasks.describe(instance.behavior.task_id)['state'], 'succeeded')

    async def test_workflow_has_one_owner(self):
        actor = {'id': 'sequence', 'behavior': 'somatic_mesh.execution_engine:WorkflowBehavior',
                 'config': {'flow': 'sequence'}}
        self.node = FabricNode(document([actor], {'sequence': {'start': 'emit', 'autostart': True,
            'nodes': {'emit': {'emit': 'done'}}}}))
        with self.assertRaisesRegex(ValueError, 'must not also autostart'):
            await self.node.boot()
