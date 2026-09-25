"""Run the optional desktop ROS action gateway from this checkout."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for source in (ROOT / 'RPStack').glob('*/*/src'):
    sys.path.insert(0, str(source))

from rpstack.node_runtime import run_manifest

if __name__ == '__main__':
    run_manifest(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).with_name('gateway.json')))
