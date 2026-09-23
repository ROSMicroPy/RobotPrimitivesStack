"""Run from the repository: python3 TestApps/slide_nodes/demo.py."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for path in list((ROOT / 'RPStack/runtime').glob('*/src')) + list((ROOT / 'RPStack/services').glob('*/src')):
    sys.path.insert(0, str(path))
from rpstack.primitive_runtime import NodeHost, NodeRuntime
from slide_simulation import simulated_node


async def main():
    folder = Path(__file__).parent
    provider = simulated_node(json.loads((folder / 'node1.json').read_text()))
    client = NodeRuntime.load(str(folder / 'node2.json'))
    host = NodeHost([provider, client])
    try:
        await host.boot()
        await client.wait()
        await client.shutdown()
        print('node2 exited; node1 state:', provider.state)
    finally:
        # The demo exits; a deployed NodeHost.run() keeps node1 resident.
        await host.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
