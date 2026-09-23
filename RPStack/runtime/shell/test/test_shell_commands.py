import asyncio
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
PACKAGE = ROOT / 'RPStack/runtime/shell'
for path in (ROOT / 'RPStack/runtime').glob('*/src'):
    sys.path.insert(0, str(path))
from rpstack.shell import registry
from rpstack.shell.commands import CommandCatalog
from rpstack.shell.async_shell import AsyncShell
from rpstack.shell.sh import Shell
from rpstack.execution_engine import TaskRegistry


class Node:
    def __init__(self):
        self.tasks, self.state, self.received = TaskRegistry(), 'running', []
    async def stop(self): self.state = 'stopped'
    async def reset(self): self.state = 'running'
    def submit(self, service, operation, arguments):
        self.received.append((service, operation, arguments))
        return self.tasks.spawn('operation', lambda: arguments, kind='operation')
    def start_flow(self, name):
        return self.tasks.spawn('flow:' + name, asyncio.Event().wait, kind='flow')
    def publish_signal(self, name, payload): self.received.append((name, payload))
    def execution_status(self): return {'runs': []}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'core').mkdir()
        self.registry_patch = patch.object(registry, 'EXT_COMMANDS_FILE', str(self.root / 'external.json'))
        self.registry_patch.start()
        self.catalog = CommandCatalog(str(self.root))
    def tearDown(self):
        self.registry_patch.stop()
        self.temp.cleanup()
    def test_lazy_discovery_and_optional_install(self):
        (self.root/'core/hello.py').write_text("raise RuntimeError('must not import')")
        self.assertEqual(self.catalog.names(), ['hello'])
        (self.root/'optional').mkdir()
        (self.root/'optional/later.py').write_text('def run(context, arguments): return arguments')
        self.assertEqual(self.catalog.groups()['optional'], ['later'])
        self.assertEqual(self.catalog.execute_sync(Shell(False, commands=self.catalog), 'later newly installed'), 'newly installed')
    def test_core_wins_and_helpers_are_ignored(self):
        (self.root/'optional').mkdir()
        (self.root/'core/stop.py').write_text("def run(context, arguments): return 'core'")
        (self.root/'optional/stop.py').write_text("raise RuntimeError('must not load')")
        (self.root/'core/_helper.py').write_text('')
        self.assertEqual(self.catalog.names(), ['stop'])
        self.assertEqual(self.catalog.execute_sync(Shell(False, commands=self.catalog), 'stop'), 'core')
    def test_external_registration(self):
        path = self.root/'external_cmd.py'
        path.write_text("class Greeting:\n    name='greet'\n    def run(self, args): return '|'.join(args)\n")
        self.assertFalse(self.catalog.names())
        registry.registercommand(str(path), 'Greeting')
        self.assertIn('greet', self.catalog.groups()['external'])
        self.assertEqual(self.catalog.execute_sync(Shell(False, commands=self.catalog), 'greet "a b"'), 'greet|a b')
    def test_init_script(self):
        (self.root/'core/value.py').write_text('def run(context, arguments): context.value = arguments')
        (self.root/'core/init.sh').write_text('# comment\nvalue first\nvalue final\n')
        self.assertEqual(Shell(True, commands=self.catalog).value, 'final')


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.node = Node()
        self.shell = AsyncShell(self.node)
        self.temp = tempfile.TemporaryDirectory()
        self.registry_patch = patch.object(registry, 'EXT_COMMANDS_FILE', str(Path(self.temp.name)/'external.json'))
        self.registry_patch.start()
    async def asyncTearDown(self):
        await self.node.tasks.cancel_kinds(('flow','operation','command'))
        self.registry_patch.stop()
        self.temp.cleanup()
    async def test_node_commands_and_json(self):
        await self.shell.command('run slide move {"label": "with spaces", "nested": [1, 2]}')
        self.assertEqual(self.node.received[-1], ('slide','move',{'label':'with spaces','nested':[1,2]}))
        await self.shell.command('signal ready {"text": "hello world"}')
        self.assertEqual(self.node.received[-1], ('ready', {'text':'hello world'}))
        await self.shell.command('flow waiting')
        task = max(self.node.tasks.records)
        output = io.StringIO()
        with contextlib.redirect_stdout(output): await self.shell.command('ps')
        self.assertIn('flow:waiting', output.getvalue())
        await self.shell.command('kill ' + str(task))
        self.assertEqual(self.node.tasks.describe(task)['state'], 'cancelled')
        await self.shell.command('stop')
        self.assertEqual(self.node.state, 'stopped')
        await self.shell.command('reset')
        self.assertEqual(self.node.state, 'running')
    async def test_wait_does_not_block_controls(self):
        waiting = asyncio.create_task(self.shell.command('wait 0.1'))
        await asyncio.sleep(0)
        await asyncio.wait_for(self.shell.command('stop'), 0.05)
        self.assertFalse(waiting.done())
        await waiting
    async def test_blocking_command_rejected_in_node_console(self):
        with self.assertRaisesRegex(ValueError, 'standalone'): await self.shell.command('python')
    async def test_shared_catalog_and_managed_sync_dispatch(self):
        shell = Shell(False, node=self.node, commands=self.shell.commands)
        shell.commands.execute_sync(shell, 'stop')
        await self.node.tasks.wait(max(self.node.tasks.records))
        self.assertEqual(self.node.state, 'stopped')
        self.assertEqual(shell.complete('rese'), ('reset ', True))
    async def test_filesystem_commands(self):
        root = Path(self.temp.name)
        directory = root/'a directory'
        await self.shell.command('mkdir "' + str(directory) + '"')
        original = directory/'one.txt'
        original.write_text('hello\n' * 500)
        copied = root/'copy'
        await self.shell.command('cp "' + str(directory) + '" "' + str(copied) + '"')
        self.assertEqual((copied/'one.txt').read_text(), original.read_text())
        output = io.StringIO()
        with contextlib.redirect_stdout(output): await self.shell.command('cat "' + str(copied/'one.txt') + '"')
        self.assertEqual(output.getvalue(), original.read_text())
        await self.shell.command('rm "' + str(copied) + '"')
        self.assertFalse(copied.exists())
        await self.shell.command('touch "' + str(root/'new file') + '"')
        self.assertTrue((root/'new file').exists())


class PackagingTests(unittest.TestCase):
    def test_packages_disjoint_and_complete(self):
        core = json.loads((PACKAGE/'package.json').read_text())
        optional = json.loads((PACKAGE/'optional/package.json').read_text())
        a, b = ({target for target,_ in doc['urls']} for doc in (core,optional))
        self.assertFalse(a & b)
        self.assertFalse(any('bin/optional/' in p for p in a))
        self.assertEqual(a | b, {str(p.relative_to(PACKAGE/'src')) for p in (PACKAGE/'src').rglob('*.py')})
        for directory,doc in ((PACKAGE,core),(PACKAGE/'optional',optional)):
            for _,source in doc['urls']: self.assertTrue((directory/source).is_file())
    def test_core_install_then_optional_overlay(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            def install(path):
                for target,source in json.loads(path.read_text())['urls']:
                    dest = stage/target
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path.parent/source, dest)
            install(PACKAGE/'package.json')
            paths = [str(stage)] + [str(p) for p in (ROOT/'RPStack/runtime').glob('*/src') if p.parent.name != 'shell']
            script = 'import sys; sys.path[:0] = ' + repr(paths) + "\nfrom rpstack.shell.commands import CommandCatalog\nfrom rpstack.shell.sh import Shell\nc=CommandCatalog()\nassert 'ps' in c.names()\nassert ('wait' in c.names()) == OPTIONAL\nShell(False).execute_command('help')\n"
            for enabled in (False,True):
                if enabled: install(PACKAGE/'optional/package.json')
                result = subprocess.run([sys.executable,'-c',script.replace('OPTIONAL',repr(enabled))],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
