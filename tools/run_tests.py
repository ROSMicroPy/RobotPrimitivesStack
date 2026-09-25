"""Run independent RPStack host suites across all responsibility groups."""
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


# Keep suites in separate interpreters so hardware fakes and event loops cannot leak.
def main():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=os.pathsep.join(str(p) for p in sorted((ROOT / 'RPStack').glob('*/*/src'))))
    failures, total = [], 0
    suites = sorted({p.parent for p in (ROOT / 'RPStack').rglob('test_*.py')})
    for suite in suites:
        result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(suite)],
                                cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
        output = result.stdout + result.stderr
        count = re.search(r'Ran (\d+) tests?', output)
        total += int(count.group(1)) if count else 0
        print(str(suite.relative_to(ROOT)), 'PASS' if result.returncode == 0 else 'FAIL', flush=True)
        if result.returncode:
            failures.append(suite)
            print(output, flush=True)
    print('{} tests across {} suites; {} failing suites'.format(total, len(suites), len(failures)))
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
