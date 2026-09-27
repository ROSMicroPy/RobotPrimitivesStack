import asyncio
import contextlib
import io
import json
import shutil
import subprocess
from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
PACKAGE = ROOT / 'RPStack/control/shell'
from rpstack.shell import registry
from rpstack.shell.commands import CommandCatalog
from rpstack.shell.async_shell import AsyncShell
from rpstack.shell.sh import Shell
from rpstack.execution_engine import TaskRegistry


class Node:
    # Prepare a minimal node with managed tasks and a record of dispatched commands.
    def __init__(self):
        self.tasks, self.state, self.received = TaskRegistry(), 'running', []
    # Simulate a successful transition to the stopped state.
    async def stop(self): self.state = 'stopped'
    # Simulate a successful return to the running state.
    async def reset(self): self.state = 'running'
    # Record service invocation and schedule a task returning the submitted arguments.
    def submit(self, service, operation, arguments):
        self.received.append((service, operation, arguments))
        return self.tasks.spawn('operation', lambda: arguments, kind='operation')
    # Create a waiting workflow task so shell cancellation can be exercised.
    def start_flow(self, name):
        return self.tasks.spawn('flow:' + name, asyncio.Event().wait, kind='flow')
    # Record signal name and payload for shell JSON parsing assertions.
    def publish_signal(self, name, payload): self.received.append((name, payload))
    # Provide an empty execution snapshot for shell status commands.
    def execution_status(self): return {'runs': []}


class DiscoveryTests(unittest.TestCase):
    # Create an isolated command tree and external registry for discovery tests.
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'core').mkdir()
        self.registry_patch = patch.object(registry, 'EXT_COMMANDS_FILE', str(self.root / 'external.json'))
        self.registry_patch.start()
        self.catalog = CommandCatalog(str(self.root))
    # Restore registry configuration and remove temporary command files.
    def tearDown(self):
        self.registry_patch.stop()
        self.temp.cleanup()
    # Ensure discovery avoids importing commands and notices newly installed optional files.
    def test_lazy_discovery_and_optional_install(self):
        (self.root/'core/hello.py').write_text("raise RuntimeError('must not import')")
        self.assertEqual(self.catalog.names(), ['hello'])
        (self.root/'optional').mkdir()
        (self.root/'optional/later.py').write_text('def run(context, arguments): return arguments')
        self.assertEqual(self.catalog.groups()['optional'], ['later'])
        self.assertEqual(self.catalog.execute_sync(Shell(False, commands=self.catalog), 'later newly installed'), 'newly installed')
    # Verify core commands override optional collisions and private helpers are not
    # discoverable.
    def test_core_wins_and_helpers_are_ignored(self):
        (self.root/'optional').mkdir()
        (self.root/'core/stop.py').write_text("def run(context, arguments): return 'core'")
        (self.root/'optional/stop.py').write_text("raise RuntimeError('must not load')")
        (self.root/'core/_helper.py').write_text('')
        self.assertEqual(self.catalog.names(), ['stop'])
        self.assertEqual(self.catalog.execute_sync(Shell(False, commands=self.catalog), 'stop'), 'core')
    # Exercise dynamic external command registration and quoted argument handling.
    def test_external_registration(self):
        path = self.root/'external_cmd.py'
        path.write_text("class Greeting:\n    name='greet'\n    def run(self, args): return '|'.join(args)\n")
        self.assertFalse(self.catalog.names())
        registry.registercommand(str(path), 'Greeting')
        self.assertIn('greet', self.catalog.groups()['external'])
        self.assertEqual(self.catalog.execute_sync(Shell(False, commands=self.catalog), 'greet "a b"'), 'greet|a b')
    # Verify initialization scripts skip comments and execute commands in order.
    def test_init_script(self):
        (self.root/'core/value.py').write_text('def run(context, arguments): context.value = arguments')
        (self.root/'core/init.sh').write_text('# comment\nvalue first\nvalue final\n')
        self.assertEqual(Shell(True, commands=self.catalog).value, 'final')


class CommandTests(unittest.IsolatedAsyncioTestCase):
    # Prepare a fake node, asynchronous shell, and isolated external-command registry.
    async def asyncSetUp(self):
        self.node = Node()
        self.shell = AsyncShell(self.node)
        self.temp = tempfile.TemporaryDirectory()
        self.registry_patch = patch.object(registry, 'EXT_COMMANDS_FILE', str(Path(self.temp.name)/'external.json'))
        self.registry_patch.start()
    # Cancel managed test work and restore temporary registry state.
    async def asyncTearDown(self):
        await self.node.tasks.cancel_kinds(('flow','operation','command'))
        self.registry_patch.stop()
        self.temp.cleanup()
    # Exercise operation/signal JSON parsing, task listing/cancellation, and node stop/reset
    # commands.
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
    # Verify a waiting shell command leaves node control commands responsive.
    async def test_wait_does_not_block_controls(self):
        waiting = asyncio.create_task(self.shell.command('wait 0.1'))
        await asyncio.sleep(0)
        await asyncio.wait_for(self.shell.command('stop'), 0.05)
        self.assertFalse(waiting.done())
        await waiting
    # Ensure terminal-owning Python mode cannot run inside the asynchronous node console.
    async def test_blocking_command_rejected_in_node_console(self):
        with self.assertRaisesRegex(ValueError, 'standalone'): await self.shell.command('python')
    # Check synchronous shell calls share command discovery and schedule asynchronous node work.
    async def test_shared_catalog_and_managed_sync_dispatch(self):
        shell = Shell(False, node=self.node, commands=self.shell.commands)
        shell.commands.execute_sync(shell, 'stop')
        await self.node.tasks.wait(max(self.node.tasks.records))
        self.assertEqual(self.node.state, 'stopped')
        self.assertEqual(shell.complete('rese'), ('reset ', True))
    # Exercise quoted paths, recursive copy/removal, file output, and file creation.
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
    # Ensure core and optional package maps are disjoint and cover every shell Python source.
    def test_packages_disjoint_and_complete(self):
        core = json.loads((PACKAGE/'package.json').read_text())
        optional = json.loads((PACKAGE/'optional/package.json').read_text())
        a, b = ({target for target,_ in doc['urls']} for doc in (core,optional))
        self.assertFalse(a & b)
        self.assertFalse(any('bin/optional/' in p for p in a))
        self.assertEqual(a | b, {str(p.relative_to(PACKAGE/'src')) for p in (PACKAGE/'src').rglob('*.py')})
        for directory,doc in ((PACKAGE,core),(PACKAGE/'optional',optional)):
            for _,source in doc['urls']: self.assertTrue((directory/source).is_file())
    # Stage core and optional installations and verify command discovery in a fresh interpreter.
    def test_core_install_then_optional_overlay(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            # Copy a package's declared files into an isolated installation tree.
            def install(path):
                for target,source in json.loads(path.read_text())['urls']:
                    dest = stage/target
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path.parent/source, dest)
            install(PACKAGE/'package.json')
            paths = [str(stage)] + [str(p) for p in (ROOT/'RPStack').glob('*/*/src') if p.parent.name != 'shell']
            script = 'import sys; sys.path[:0] = ' + repr(paths) + "\nfrom rpstack.shell.commands import CommandCatalog\nfrom rpstack.shell.sh import Shell\nc=CommandCatalog()\nassert 'ps' in c.names()\nassert ('wait' in c.names()) == OPTIONAL\nShell(False).execute_command('help')\n"
            for enabled in (False,True):
                if enabled: install(PACKAGE/'optional/package.json')
                result = subprocess.run([sys.executable,'-c',script.replace('OPTIONAL',repr(enabled))],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)


class DownloadTests(unittest.TestCase):
    # Exercise real command discovery with a fake HTTP response and arbitrary binary data.
    def test_wget_dispatch_preserves_binary_and_reads_until_eof(self):
        from unittest.mock import Mock
        response = Mock()
        response.raw.read.side_effect = [b'\x00\xff', b'\x80data', b'']
        requests = Mock()
        requests.get.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'download file'
            with patch.dict(sys.modules, {'requests': requests}), contextlib.redirect_stdout(io.StringIO()):
                CommandCatalog().execute_sync(Shell(False), 'wget https://example.invalid/file "' + str(destination) + '"')
            self.assertEqual(destination.read_bytes(), b'\x00\xff\x80data')
        response.close.assert_called_once_with()
        requests.get.assert_called_once_with('https://example.invalid/file')

    # Release the HTTP response even when the requested output directory does not exist.
    def test_wget_closes_response_on_output_failure(self):
        from unittest.mock import Mock
        response = Mock()
        requests = Mock()
        requests.get.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'missing' / 'file'
            with patch.dict(sys.modules, {'requests': requests}), self.assertRaises(OSError):
                CommandCatalog().execute_sync(Shell(False), 'wget https://example.invalid/file "' + str(destination) + '"')
        response.close.assert_called_once_with()


class DirectCommandTests(unittest.TestCase):
    # Move a quoted filename through the public shell command interface.
    def test_move_uses_two_user_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source file'
            destination = Path(directory) / 'destination file'
            source.write_text('payload')
            with contextlib.redirect_stdout(io.StringIO()):
                CommandCatalog().execute_sync(Shell(False), 'mv "' + str(source) + '" "' + str(destination) + '"')
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_text(), 'payload')

    # Verify optional commands parse their first argument without synthetic script prefixes.
    def test_frequency_uses_first_user_argument(self):
        from unittest.mock import Mock
        machine = Mock()
        with patch.dict(sys.modules, {'machine': machine}), contextlib.redirect_stdout(io.StringIO()):
            CommandCatalog().execute_sync(Shell(False), 'freq 80')
        machine.freq.assert_called_once_with(80000000)
