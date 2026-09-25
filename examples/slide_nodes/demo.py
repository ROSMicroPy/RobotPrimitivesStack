"""Run from the repository: python3 examples/slide_nodes/demo.py."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / 'RPStack').glob('*/*/src'):
    sys.path.insert(0, str(path))
from rpstack.node_runtime import NodeRuntime
from slide_simulation import simulated_node


async def main():
    folder = Path(__file__).parent
    provider = simulated_node(json.loads((folder / 'node1.json').read_text()))
    client = NodeRuntime.load(str(folder / 'node2.json'))
    try:
        await provider.boot()
        await provider.calibrate("slide", {"steps": 1000})
        await client.boot()
        await client.wait()
        await client.shutdown()
        print('node2 exited; node1 state:', provider.state)
    finally:
        # The demo exits; a deployed NodeHost.run() keeps node1 resident.
        await client.shutdown()
        await provider.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
