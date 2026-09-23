"""Standalone terminal front end. Command implementations are discovered in bin."""
import os
from .cmd import Cmd
from .commands import CommandCatalog

_shell_instance = None


class Shell(Cmd):
    def __init__(self, run_init=True, node=None, commands=None):
        super().__init__()
        from .async_shell import current_node
        self.node = node if node is not None else current_node
        self.commands = commands or CommandCatalog()
        self.session = None
        self.update_prompt()
        if run_init and 'init' in self.commands.names():
            self.execute_command('init')

    def update_prompt(self):
        if self.session is None:
            self.prompt = '{} upy$ '.format(os.getcwd())

    def request_exit(self):
        self.stop()

    def complete(self, line):
        if self.session is not None:
            return line, False
        parts = line.split(' ')
        if len(parts) == 1:
            matches = self.commands.names(parts[0])
        else:
            matches = [name for name in os.listdir('.') if name.startswith(parts[-1])]
        if len(matches) == 1:
            return ' '.join(parts[:-1] + [matches[0]]) + ' ', True
        if matches:
            print('\n' + '\t'.join(matches))
        return line, bool(matches)

    def should_execute_empty_line(self):
        return self.session is not None and self.session.should_execute_empty_line()

    def execute_command(self, line):
        try:
            if self.session is not None:
                self.session.execute_command(line)
            else:
                result = self.commands.execute_sync(self, line)
                if result is not None:
                    print(result)
        except (Exception, KeyboardInterrupt) as error:
            print('Error: ' + str(error))
        self.update_prompt()

    @staticmethod
    def cmd(command, run_init=True):
        shell = Shell(run_init=run_init)
        shell.execute_command(command)
        return shell


def start(run_init=True):
    global _shell_instance
    _shell_instance = Shell(run_init=run_init)
    _shell_instance.cmdloop()
    return _shell_instance


def cmd(command, run_init=True):
    return Shell.cmd(command, run_init=run_init)


def all_commands(start=''):
    return CommandCatalog().names(start)


def has_command(name):
    return name in CommandCatalog().names()


def execute_command(command):
    shell = _shell_instance or Shell(run_init=False)
    return shell.commands.execute_sync(shell, command)
