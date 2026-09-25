import asyncio
from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest
from rpstack.execution_engine import ExecutionEngine, TaskRegistry
from rpstack.signals import SignalBus


class EngineTests(unittest.IsolatedAsyncioTestCase):
    # Ensure workflow subscriptions exist before an action can publish its completion signal.
    async def test_signal_published_during_action_is_not_lost(self):
        tasks = TaskRegistry()
        # Publish completion immediately from inside the simulated action.
        async def action(*args):
            engine.signals.publish('finished', {'ok': True})
        engine = ExecutionEngine(tasks, action)
        task_id = engine.start('test', {'start': 'a', 'nodes': {
            'a': {'service': 's', 'operation': 'run', 'wait_for': 'finished', 'timeout_s': 0.1}}})
        result = await tasks.wait(task_id)
        self.assertEqual(result['payload'], {'ok': True})
        self.assertEqual(engine.signals.subscribers, {})

    # Verify a timed-out signal wait follows its configured recovery branch.
    async def test_wait_timeout_routes_to_error_node(self):
        calls = []
        # Record recovery invocation and return a recognizable recovery result.
        async def action(*args):
            calls.append(args)
            return 'recovered'
        tasks = TaskRegistry()
        engine = ExecutionEngine(tasks, action)
        task_id = engine.start('test', {'start': 'wait', 'nodes': {
            'wait': {'wait_for': 'never', 'timeout_s': 0.001, 'on_error': 'recover'},
            'recover': {'service': 's', 'operation': 'cleanup'}}})
        self.assertEqual(await tasks.wait(task_id), 'recovered')
        self.assertEqual(len(calls), 1)

    # Check independent delivery and explicit overflow errors for bounded subscriptions.
    async def test_independent_waiters_and_bounded_event_queue(self):
        bus = SignalBus(queue_limit=1)
        first, second = bus.subscribe('event'), bus.subscribe('event')
        bus.publish('event', 1)
        self.assertEqual((await first.get())['payload'], 1)
        self.assertEqual((await second.get())['payload'], 1)
        bus.publish('event', 2)
        bus.publish('event', 3)
        with self.assertRaisesRegex(RuntimeError, 'overflow'):
            await first.get()
        first.close()
        second.close()
        self.assertEqual(bus.subscribers, {})

    # Verify completed task history is bounded and immediate cancellation reaches a terminal
    # state.
    async def test_history_is_bounded_and_immediate_cancel_completes(self):
        tasks = TaskRegistry(history_limit=2)
        for _ in range(5):
            task_id = tasks.spawn('done', lambda: 1)
            self.assertEqual(await tasks.wait(task_id), 1)
        self.assertEqual(len(tasks.records), 2)
        task_id = tasks.spawn('wait', asyncio.Event().wait)
        await tasks.cancel(task_id)
        self.assertEqual(tasks.describe(task_id)['state'], 'cancelled')
