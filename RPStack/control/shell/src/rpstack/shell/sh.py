"""Standalone terminal front end. Command implementations are discovered in bin."""
import os
from .cmd import Cmd
from .commands import CommandCatalog

_shell_instance = None


class Shell(Cmd):
    # Attach command discovery and optional node context, then run the initialization command if
    # present.
    def __init__(self, run_init=True, node=None, commands=None):
        super().__init__()
        from .async_shell import current_node
        self.node = node if node is not None else current_node
        self.commands = commands or CommandCatalog()
        self.session = None
        self.update_prompt()
        if run_init and 'init' in self.commands.names():
            self.execute_command('init')

    # Show the working directory unless an interactive session owns the prompt.
    def update_prompt(self):
        if self.session is None:
            self.prompt = '{} upy$ '.format(os.getcwd())

    # Stop the underlying terminal command loop.
    def request_exit(self):
        self.stop()

    # Complete command names or local filenames, leaving session-owned input untouched.
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

    # Delegate empty-line handling to an active interactive session.
    def should_execute_empty_line(self):
        return self.session is not None and self.session.should_execute_empty_line()

    # Dispatch to the active session or command catalog, reporting failures and refreshing the
    # prompt.
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

    # Create a shell, execute one command, and return the shell for further use.
    @staticmethod
    def cmd(command, run_init=True):
        shell = Shell(run_init=run_init)
        shell.execute_command(command)
        return shell


# Create the shared shell instance and enter its interactive command loop.
def start(run_init=True):
    global _shell_instance
    _shell_instance = Shell(run_init=run_init)
    _shell_instance.cmdloop()
    return _shell_instance


# Expose one-command shell execution through the module-level convenience API.
def cmd(command, run_init=True):
    return Shell.cmd(command, run_init=run_init)


# List catalog commands matching an optional prefix.
def all_commands(start=''):
    return CommandCatalog().names(start)


# Check whether a command name is currently discoverable.
def has_command(name):
    return name in CommandCatalog().names()


# Run a command through the shared shell or a temporary shell without initialization.
def execute_command(command):
    shell = _shell_instance or Shell(run_init=False)
    return shell.commands.execute_sync(shell, command)
