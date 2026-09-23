"""A coordinator advances a robot-wide workflow using entity-scoped signals."""
from .tasks import asyncio
from rpstack.signals import SignalBus
from rpstack.signals.model import nonce

# Existing callers can use the event vocabulary; there is only one signal bus.
EventBus = SignalBus


class ExecutionEngine:
    def __init__(self, tasks, invoke, signals=None, remote=None):
        self.tasks, self.invoke, self.remote = tasks, invoke, remote
        self.signals = signals or SignalBus()
        self.events = self.signals
        self.runs = {}

    def start(self, name, flow):
        run_id = self.signals.node_id + '/' + self.signals.boot + '/' + nonce()
        task_id = self.tasks.spawn('flow:' + name, self.run, flow, run_id, kind='flow', owner=name)
        self.runs[task_id] = {'run_id': run_id, 'flow': name, 'step': None, 'state': 'pending', 'revision': 0}
        for old in tuple(self.runs):
            if old not in self.tasks.records:
                del self.runs[old]
        return task_id

    def snapshot(self):
        return [dict(value, task_id=key) for key, value in self.runs.items() if key in self.tasks.records]

    def _state(self, run_id, state, step):
        record = next((r for r in self.runs.values() if r['run_id'] == run_id), None)
        if record is not None:
            record.update(state=state, step=step, revision=record['revision'] + 1)
            try:
                self.signals.publish('_rp.state', dict(record), correlation=run_id)
            except (ValueError, RuntimeError):
                pass  # State telemetry never prevents cancellation/cleanup.

    async def run(self, flow, run_id=None):
        run_id = run_id or self.signals.node_id + '/' + nonce()
        subscriptions, nodes = {}, flow['nodes']
        current, result = flow['start'], None
        try:
            # Subscribe before actions. Correlated waits isolate simultaneous runs;
            # uncorrelated waits intentionally consume external robot-wide events.
            for key, node in nodes.items():
                if node.get('wait_for'):
                    subscriptions[key] = self.signals.subscribe(node['wait_for'],
                        correlation=run_id if node.get('correlated', False) else None,
                        source=node.get('signal_source'))
            while current:
                node = nodes[current]
                self._state(run_id, 'running', current)
                try:
                    if 'operation' in node:
                        target = node.get('node', self.signals.node_id)
                        if target == self.signals.node_id:
                            result = await self.invoke(node['service'], node['operation'], node.get('arguments', {}))
                        else:
                            if self.remote is None:
                                raise RuntimeError('remote execution is not configured')
                            result = await self.remote.invoke(target, node['service'], node['operation'],
                                node.get('arguments', {}), run_id, node.get('timeout_s', 30))
                        if result is False:
                            raise RuntimeError('workflow operation returned false')
                    if node.get('wait_for'):
                        self._state(run_id, 'waiting', current)
                        result = await subscriptions[current].get(node.get('timeout_s'))
                    if node.get('emit'):
                        self.signals.publish(node['emit'], result, correlation=run_id,
                                             routes=node.get('routes'))
                    current = node.get('next')
                except Exception:
                    if not node.get('on_error'):
                        raise
                    current = node['on_error']
                await asyncio.sleep(0)
            self._state(run_id, 'succeeded', None)
            return result
        except asyncio.CancelledError:
            self._state(run_id, 'cancelled', current)
            raise
        except Exception:
            self._state(run_id, 'failed', current)
            raise
        finally:
            for sub in subscriptions.values():
                sub.close()
