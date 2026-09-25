"""Nonblocking node console. Every background operation belongs to the node."""
import sys
from rpstack.support import asyncio
from .commands import CommandCatalog

current_node = None


class AsyncShell:
    # Bind the shell to a node and prepare nonblocking input polling and command discovery.
    def __init__(self, node, poll_interval_s=0.02, commands=None):
        self.node = node
        self.poll_interval_s = poll_interval_s
        self.poller = None
        self.commands = commands or CommandCatalog()
        self.is_async = True
        self._exit_requested = False

    # Attach stdin polling, publish the current node, and display available commands.
    def start(self):
        global current_node
        current_node = self.node
        import select
        self.poller = select.poll()
        self.poller.register(sys.stdin, select.POLLIN)
        print("RPStack: " + " | ".join(self.commands.names()))

    # Execute a catalog command asynchronously and print its returned value when present.
    async def command(self, line):
        result = await self.commands.execute(self, line)
        if result is not None:
            print(result)
        return result

    # Request that the input loop stop accepting commands.
    def request_exit(self):
        self._exit_requested = True

    # Run one shell command and display failures without terminating the input loop.
    async def _command(self, line):
        try:
            await self.command(line)
        except Exception as error:
            print("Error: " + str(error))

    # Edit terminal input and schedule commands as managed tasks while keeping node work
    # responsive.
    async def run(self):
        line = ""
        sys.stdout.write("rp> ")
        while True:
            if self._exit_requested:
                await asyncio.Event().wait()
            if self.poller.poll(0):
                char = sys.stdin.read(1)
                if not char:
                    await asyncio.Event().wait()
                if char in ("\r", "\n"):
                    if line:
                        print()
                        self.node.tasks.spawn("shell:" + line.split()[0], self._command, line, kind="command")
                        line = ""
                        sys.stdout.write("rp> ")
                elif char in ("\x7f", "\b"):
                    if line:
                        line = line[:-1]
                        sys.stdout.write("\b \b")
                elif char == "\x03":
                    line = ""
                    self.node.tasks.spawn("shell:stop", self._command, "stop", kind="command")
                elif char >= " " and len(line) < 1024:
                    line += char
                    sys.stdout.write(char)
            await asyncio.sleep(self.poll_interval_s)

    # Unregister terminal input and clear the shared current-node reference.
    def stop(self):
        global current_node
        if self.poller:
            self.poller.unregister(sys.stdin)
        current_node = None
