"""Run a three-node robot entirely from manifests, without robot hardware."""
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / 'RPStack').glob('*/*/src'):
    sys.path.insert(0, str(path))
from rpstack.node_runtime.node import NodeRuntime


async def main():
    nodes = []
    try:
        for name in ('arm', 'base', 'controller'):
            node = NodeRuntime.load(str(Path(__file__).with_name(name + '.json')))
            nodes.append(node)
            await node.boot()
        controller = nodes[-1]
        task = next(task for task, run in controller.engine.runs.items() if run['flow'] == 'reach')
        print('Robot workflow result:', await controller.tasks.wait(task))
        for node in nodes:
            print(node.signals.node_id, node.execution_status())
    finally:
        for node in reversed(nodes):
            await node.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
