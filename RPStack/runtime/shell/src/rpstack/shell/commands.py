"""Discover installed command groups and invoke lazy command modules."""
import os
from rpstack.execution_engine import asyncio
from . import registry
from .support import split_arguments


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


def is_async(result):
    return hasattr(result, '__await__') or hasattr(result, 'send')


class CommandCatalog:
    def __init__(self, root=None):
        self.root = root or command_root()
        self.external_entries = None
        self.external = {}

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

    def groups(self):
        groups = {'core': [], 'optional': [], 'external': []}
        for name, entry in self.discover().items():
            groups[entry['group']].append(name)
        return groups

    def names(self, prefix=''):
        return sorted(name for name in self.discover() if name.startswith(prefix))

    def _load(self, entry):
        module_name = 'rpstack.shell.bin.' + entry['group'] + '.' + entry['name']
        if entry['extension'] == 'mpy':
            module = __import__(module_name, None, None, ('run',))
            return module.run, getattr(module, 'FOREGROUND_ONLY', False)
        namespace = {'__name__': module_name, '__file__': entry['path']}
        with open(entry['path']) as handle:
            exec(handle.read(), namespace)
        return namespace['run'], namespace.get('FOREGROUND_ONLY', False)

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

    def _invoke(self, context, entry, arguments):
        if entry['group'] == 'external':
            instance = entry['instance']
            handler = getattr(instance, 'run', None) or instance.__main__
            return handler([entry['name']] + split_arguments(arguments))
        handler, foreground = self._load(entry)
        if foreground and (context.node is not None or getattr(context, 'is_async', False)):
            raise ValueError(entry['name'] + ' requires the standalone shell; it takes over the terminal or blocks')
        return handler(context, arguments)

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
