"""Nonblocking node console. Every background operation belongs to the node."""
import sys
try:
    import ujson as json
except ImportError:
    import json
from rpstack.execution_engine import asyncio

current_node = None


def print_tasks(node):
    print("ID\tSTATE\t\tKIND\t\tNAME")
    for item in node.tasks.snapshot():
        print("{}\t{}\t{}\t{}".format(item["id"], item["state"], item["kind"], item["name"]))


class AsyncShell:
    def __init__(self, node, poll_interval_s=0.02):
        self.node = node
        self.poll_interval_s = poll_interval_s
        self.poller = None

    def start(self):
        global current_node
        current_node = self.node
        import select
        self.poller = select.poll()
        self.poller.register(sys.stdin, select.POLLIN)
        print("RPStack: ps | stop | reset | kill ID | run SERVICE OP [JSON] | flow NAME | signal NAME [JSON]")

    async def command(self, line):
        parts = line.strip().split(None, 3)
        if not parts:
            return
        command = parts[0]
        if command == "ps":
            print_tasks(self.node)
        elif command == "stop":
            await self.node.stop()
            print("Node stopped; shell and HTTP remain available")
        elif command == "reset":
            await self.node.reset()
            print("Node ready")
        elif command == "kill":
            task_id = int(parts[1])
            if self.node.tasks.records[task_id]["kind"] not in ("operation", "flow"):
                raise ValueError("use stop to stop services")
            await self.node.tasks.cancel(task_id)
        elif command == "run":
            args = json.loads(parts[3]) if len(parts) > 3 else {}
            print("Task {}".format(self.node.submit(parts[1], parts[2], args)))
        elif command == "flow":
            print("Task {}".format(self.node.start_flow(parts[1])))
        elif command == "signal":
            signal_parts = line.split(None, 2)
            payload = json.loads(signal_parts[2]) if len(signal_parts) > 2 else None
            self.node.engine.events.publish(signal_parts[1], payload)
        elif command == "status":
            print(self.node.state)
        else:
            raise ValueError("unknown command: " + command)

    async def _command(self, line):
        try:
            await self.command(line)
        except Exception as error:
            print("Error: " + str(error))

    async def run(self):
        line = ""
        sys.stdout.write("rp> ")
        while True:
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

    def stop(self):
        global current_node
        if self.poller:
            self.poller.unregister(sys.stdin)
        current_node = None
