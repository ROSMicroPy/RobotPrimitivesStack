"""Generate disjoint core and optional mip packages from the shell source tree."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src'
OPTIONAL_SUPPORT = {'microWebSrv.py', 'utelnetserver.py'}


# Partition shell sources into core/optional packages and regenerate local and remote install
# manifests.
def generate():
    core, optional = [], []
    for path in sorted(SOURCE.rglob('*.py')):
        relative = path.relative_to(SOURCE)
        is_optional = '/bin/optional/' in '/' + str(relative) or path.name in OPTIONAL_SUPPORT
        if is_optional:
            optional.append([str(relative), '../src/' + str(relative)])
        else:
            core.append([str(relative), 'src/' + str(relative)])
    packages = [
        (ROOT, 'rp-shell', core, [['github:ROSMicroPy/RobotPrimitivesStack/RPStack/runtime/execution_engine', 'archdef'], ['github:ROSMicroPy/RobotPrimitivesStack/RPStack/foundation/support', 'archdef']]),
        (ROOT / 'optional', 'rp-shell-optional', optional, [['github:ROSMicroPy/RobotPrimitivesStack/RPStack/control/shell', 'archdef']]),
    ]
    for directory, name, urls, dependencies in packages:
        directory.mkdir(exist_ok=True)
        for local in (False, True):
            deps = ([['../package.local.json', 'latest']] if name == 'rp-shell-optional' else []) if local else dependencies
            document = {'name': name, 'version': '3.0.0', 'urls': urls, 'deps': deps}
            filename = 'package.local.json' if local else 'package.json'
            (directory / filename).write_text(json.dumps(document, indent=2) + '\n')


if __name__ == '__main__':
    generate()
