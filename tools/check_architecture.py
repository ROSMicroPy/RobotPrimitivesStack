"""Verify package sources, dependency closures, and isolated installed imports."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'github:ROSMicroPy/RobotPrimitivesStack/'


# Resolve repository dependencies without fetching optional third-party libraries.
def dependency(manifest, reference):
    if reference.startswith(PREFIX):
        path = ROOT / reference[len(PREFIX):]
        return path if path.suffix == '.json' else path / 'package.json'
    if ':' not in reference:
        path = manifest.parent / reference
        return path if path.suffix == '.json' else path / 'package.json'
    return None


# Install exactly the declared dependency closure, detecting cycles and conflicting files.
def stage(manifest, destination, done=None, active=None):
    done = set() if done is None else done
    active = set() if active is None else active
    manifest = manifest.resolve()
    if manifest in active:
        raise AssertionError('package dependency cycle: ' + str(manifest))
    if manifest in done:
        return
    active.add(manifest)
    document = json.loads(manifest.read_text())
    for reference, _ in document.get('deps', []):
        path = dependency(manifest, reference)
        if path is not None:
            stage(path, destination, done, active)
    for target, source in document.get('urls', []):
        source = manifest.parent / source
        output = destination / target
        if output.exists() and output.read_bytes() != source.read_bytes():
            raise AssertionError('conflicting installed file: ' + target)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
    active.remove(manifest)
    done.add(manifest)


# Probe an installation with repository source paths and user site packages excluded.
def probe(manifest, script):
    with tempfile.TemporaryDirectory() as directory:
        destination = Path(directory)
        stage(ROOT / manifest, destination)
        code = 'import sys; sys.path.insert(0, ' + repr(directory) + ')\n' + script
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd=directory,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(manifest + '\n' + result.stdout + result.stderr)


# Check every source map before testing representative standalone package installations.
def main():
    manifests = [p for base in ('RPStack', 'examples') for p in (ROOT / base).rglob('package*.json')]
    for manifest in manifests:
        document = json.loads(manifest.read_text())
        for _, source in document.get('urls', []):
            if ':' not in source:
                assert (manifest.parent / source).is_file(), (manifest, source)
        for reference, _ in document.get('deps', []):
            path = dependency(manifest, reference)
            if path is not None:
                assert path.is_file(), (manifest, reference)
    # Stage every map so file conflicts and dependency cycles cannot hide in an unused package.
    for manifest in manifests:
        with tempfile.TemporaryDirectory() as directory:
            stage(manifest, Path(directory))
    lean = "\nassert not any(n.startswith(('rpstack.execution_engine', 'rpstack.signals', 'rpstack.node_runtime')) for n in sys.modules)\n"
    probe('RPStack/foundation/support/package.json', 'from rpstack.support import asyncio, call, now_ms, elapsed_ms\n' + lean)
    for package, name in [('motor_control', 'Motor'), ('distance_sensor', 'DistanceSensor'), ('distance_to_position', 'DistanceToPositionAdapter')]:
        probe('RPStack/services/' + package + '/package.json', 'from rpstack.' + package + ' import ' + name + lean)
    probe('RPStack/apps/slide_commands/package.json', 'from rpstack.apps.slide_commands import MoveOnceApp\nassert "rpstack.linear_slide" not in sys.modules\nassert "rpstack.node_runtime" not in sys.modules')
    packages = {
        'runtime/node_runtime': 'from rpstack.node_runtime import NodeRuntime, ServiceRegistry',
        'transports/espnow': 'from rpstack.espnow import Framing, EspNowTransport\nfrom rpstack.espnow.shared import SharedEspNowTransport',
        'transports/ros_signals': 'from rpstack.ros_signals import RosTransport',
        'apps/robot_gateway': 'from rpstack.apps.robot_gateway import GatewayApp',
        'platform/env': 'from rpstack.env.cmds.envcmd import EnvCommand\nfrom rpstack.env.cmds.exportcmd import ExportCommand',
        'services/linear_slide': 'from rpstack.linear_slide import LinearSlide\nassert "rpstack.apps.slide_commands" not in sys.modules',
    }
    for package, script in packages.items():
        probe('RPStack/' + package + '/package.json', script)
    # Local example manifests must supply dependencies even without remote recursion.
    for example in ('linear_slide', 'mesh_gateway', 'slide_nodes'):
        probe('examples/' + example + '/package.json', '''
import json
from pathlib import Path
from rpstack.node_runtime.manifest import load_entry_point
for path in Path('.').glob('*.json'):
    document = json.loads(path.read_text())
    if document.get('manifest') != 'rp.node/v1':
        continue
    specs = document.get('runtime', []) + document.get('apps', []) + document.get('signals', {}).get('transports', [])
    for spec in specs:
        load_entry_point(spec['entry_point'])
    for component in document.get('components', {}).values():
        if component.get('entry_point'):
            load_entry_point(component['entry_point'])
''')
    print('Architecture checks passed:', len(manifests), 'source/dependency maps and 14 isolated installations.')


if __name__ == '__main__':
    main()
