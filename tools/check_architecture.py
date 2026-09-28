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
    manifests = [p for base in ('SomaticMesh', 'examples') for p in (ROOT / base).rglob('package*.json')]
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
    lean = "\nassert not any(n.startswith(('somatic_mesh.execution_engine', 'somatic_mesh.signals', 'somatic_mesh.fabric_node')) for n in sys.modules)\n"
    probe('SomaticMesh/foundation/support/package.json', 'from somatic_mesh.support import asyncio, call, now_ms, elapsed_ms\n' + lean)
    for package, name in [('motor_control', 'Motor'), ('distance_sensor', 'DistanceSensor'), ('distance_to_position', 'DistanceToPositionAdapter')]:
        probe('SomaticMesh/services/' + package + '/package.json', 'from somatic_mesh.' + package + ' import ' + name + lean)
    probe('SomaticMesh/behaviors/slide_commands/package.json', 'from somatic_mesh.behaviors.slide_commands import MoveOnceBehavior\nassert "somatic_mesh.linear_slide" not in sys.modules\nassert "somatic_mesh.fabric_node" not in sys.modules')
    packages = {
        'runtime/fabric_node': 'from somatic_mesh.fabric_node import FabricNode, ServiceRegistry',
        'transports/espnow': 'from somatic_mesh.espnow import Framing, EspNowTransport\nfrom somatic_mesh.espnow.shared import SharedEspNowTransport',
        'transports/ros_signals': 'from somatic_mesh.ros_signals import RosTransport',
        'behaviors/robot_gateway': 'from somatic_mesh.behaviors.robot_gateway import GatewayBehavior',
        'behaviors/ros_gateway': 'from somatic_mesh.behaviors.ros_gateway import SlideRosBehavior\nassert "rclpy" not in sys.modules',
        'platform/env': 'from somatic_mesh.env.cmds.envcmd import EnvCommand\nfrom somatic_mesh.env.cmds.exportcmd import ExportCommand',
        'services/linear_slide': 'from somatic_mesh.linear_slide import LinearSlide\nassert "somatic_mesh.behaviors.slide_commands" not in sys.modules',
    }
    for package, script in packages.items():
        probe('SomaticMesh/' + package + '/package.json', script)
    # Local example manifests must supply dependencies even without remote recursion.
    for example in ('linear_slide', 'mesh_gateway', 'slide_nodes', 'ros_slide'):
        probe('examples/' + example + '/package.json', '''
import json
from pathlib import Path
from somatic_mesh.fabric_node.manifest import load_entry_point
for path in Path('.').glob('*.json'):
    document = json.loads(path.read_text())
    if document.get('manifest') != 'somatic.node/v1':
        continue
    specs = document.get('runtime', []) + document.get('signals', {}).get('transports', [])
    for spec in specs:
        load_entry_point(spec['entry_point'])
    for actor in document.get('actors', []):
        load_entry_point(actor['behavior'])
    for component in document.get('components', {}).values():
        if component.get('entry_point'):
            load_entry_point(component['entry_point'])
''')
    print('Architecture checks passed:', len(manifests), 'source/dependency maps and 16 isolated installations.')


if __name__ == '__main__':
    main()
