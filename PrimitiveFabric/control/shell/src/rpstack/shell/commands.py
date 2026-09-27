"""Discover installed command groups and invoke lazy command modules."""
import os
from rpstack.support import asyncio
from . import registry
from .support import split_arguments


# Locate installed command files using source-relative and device deployment paths.
def command_root():
    candidates = []
    try:
        candidates.append(__file__.rsplit('/', 1)[0] + '/bin')
    except NameError:
        pass
    candidates.extend(('/lib/rpstack/shell/bin', 'rpstack/shell/bin'))
    for path in candidates:
        try:
            os.listdir(path + '/core')
            return path
        except OSError:
            pass
    return candidates[0]


# Recognize both CPython awaitables and MicroPython coroutine generators.
def is_async(result):
    return hasattr(result, '__await__') or hasattr(result, 'send')


class CommandCatalog:
    # Select the command root and prepare caching for external command registrations.
    def __init__(self, root=None):
        self.root = root or command_root()
        self.external_entries = None
        self.external = {}

    # Discover core, optional, and external commands while preserving core command precedence.
    def discover(self):
        found = {}
        # Core always wins; optional installations cannot replace node controls.
        for group in ('core', 'optional'):
            directory = self.root + '/' + group
            try:
                files = sorted(os.listdir(directory))
            except OSError:
                continue
            for filename in files:
                name, extension = filename.rsplit('.', 1) if '.' in filename else (filename, '')
                if name.startswith('_') or extension not in ('py', 'mpy', 'sh') or name in found:
                    continue
                found[name] = {'name': name, 'group': group, 'path': directory + '/' + filename,
                               'extension': extension}
        entries = registry.read_ext_registry()
        if entries != self.external_entries:
            self.external_entries, self.external = entries, {}
            for entry in entries:
                try:
                    loaded = registry.load_external_command(entry)
                    self.external[loaded['name']] = loaded
                except Exception as error:
                    print('Unable to load external command: ' + str(error))
        for name, entry in self.external.items():
            if name not in found:
                found[name] = dict(entry, group='external')
        return found

    # Group discovered command names by installation category.
    def groups(self):
        groups = {'core': [], 'optional': [], 'external': []}
        for name, entry in self.discover().items():
            groups[entry['group']].append(name)
        return groups

    # Return sorted command names matching an optional completion prefix.
    def names(self, prefix=''):
        return sorted(name for name in self.discover() if name.startswith(prefix))

    # Load a Python or compiled command and discover whether it requires terminal ownership.
    def _load(self, entry):
        module_name = 'rpstack.shell.bin.' + entry['group'] + '.' + entry['name']
        if entry['extension'] == 'mpy':
            module = __import__(module_name, None, None, ('run',))
            return module.run, getattr(module, 'FOREGROUND_ONLY', False)
        namespace = {'__name__': module_name, '__file__': entry['path']}
        with open(entry['path']) as handle:
            exec(handle.read(), namespace)
        return namespace['run'], namespace.get('FOREGROUND_ONLY', False)

    # Split a command line, reject background syntax, and resolve its catalog entry.
    def _resolve(self, line):
        parts = line.strip().split(None, 1)
        if not parts:
            return None, ''
        if line.rstrip().endswith('&'):
            raise ValueError('commands already run as managed tasks; omit &')
        entry = self.discover().get(parts[0])
        if entry is None:
            raise ValueError('unknown command: ' + parts[0])
        return entry, parts[1] if len(parts) > 1 else ''

    # Invoke external or packaged commands, enforcing restrictions on foreground-only tools.
    def _invoke(self, context, entry, arguments):
        if entry['group'] == 'external':
            instance = entry['instance']
            handler = instance.run
            return handler([entry['name']] + split_arguments(arguments))
        handler, foreground = self._load(entry)
        if foreground and (context.node is not None or getattr(context, 'is_async', False)):
            raise ValueError(entry['name'] + ' requires the standalone shell; it takes over the terminal or blocks')
        return handler(context, arguments)

    # Execute scripts line by line or await a command's asynchronous result.
    async def execute(self, context, line):
        entry, arguments = self._resolve(line)
        if entry is None:
            return
        if entry.get('extension') == 'sh':
            with open(entry['path']) as handle:
                for line in handle:
                    if line.strip() and not line.lstrip().startswith('#'):
                        await self.execute(context, line)
            return
        result = self._invoke(context, entry, arguments)
        return await result if is_async(result) else result

    # Bridge synchronous callers to immediate results, a standalone event loop, or managed node
    # tasks.
    def execute_sync(self, context, line):
        entry, arguments = self._resolve(line)
        if entry is None:
            return
        result = self.execute(context, line) if entry.get('extension') == 'sh' else self._invoke(context, entry, arguments)
        if not is_async(result):
            return result
        if context.node is None:
            return asyncio.run(result)
        try:
            task_id = context.node.tasks.spawn('shell:' + entry['name'], lambda: result, kind='command')
        except BaseException:
            if hasattr(result, 'close'):
                result.close()
            raise
        print('Task {}'.format(task_id))
