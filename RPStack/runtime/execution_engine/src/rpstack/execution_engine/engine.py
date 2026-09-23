"""Bounded broadcast subscriptions and cancellable declarative workflows."""
from .tasks import asyncio


class Subscription:
    def __init__(self, bus, name, limit):
        self.bus, self.name, self.limit = bus, name, limit
        self.items = []
        self.ready = asyncio.Event()
        self.overflow = False

    async def get(self, timeout=None):
        async def receive():
            while not self.items and not self.overflow:
                await self.ready.wait()
            if self.overflow:
                raise RuntimeError("event queue overflow: " + self.name)
            item = self.items.pop(0)
            if not self.items:
                self.ready.clear()
            return item
        if timeout is None:
            return await receive()
        return await asyncio.wait_for(receive(), timeout)

    def close(self):
        subscribers = self.bus.subscribers.get(self.name, [])
        if self in subscribers:
            subscribers.remove(self)
        if not subscribers:
            self.bus.subscribers.pop(self.name, None)


class EventBus:
    def __init__(self, queue_limit=16):
        self.queue_limit = queue_limit
        self.subscribers = {}

    def subscribe(self, name):
        sub = Subscription(self, name, self.queue_limit)
        self.subscribers.setdefault(name, []).append(sub)
        return sub

    def publish(self, name, payload=None):
        for sub in self.subscribers.get(name, ()):
            if len(sub.items) >= sub.limit:
                sub.overflow = True
            else:
                sub.items.append({"name": name, "payload": payload})
            sub.ready.set()


class ExecutionEngine:
    def __init__(self, tasks, invoke):
        self.tasks = tasks
        self.invoke = invoke
        self.events = EventBus()

    def start(self, name, flow):
        return self.tasks.spawn("flow:" + name, self.run, flow, kind="flow", owner=name)

    async def run(self, flow):
        subscriptions = {}
        nodes = flow["nodes"]
        # Subscribe before any action: signals produced during actions are retained.
        for node in nodes.values():
            if node.get("wait_for"):
                name = node["wait_for"]
                if name not in subscriptions:
                    subscriptions[name] = self.events.subscribe(name)
        current = flow["start"]
        result = None
        try:
            while current:
                node = nodes[current]
                try:
                    if "operation" in node:
                        result = await self.invoke(node["service"], node["operation"], node.get("arguments", {}))
                        if result is False:
                            raise RuntimeError("workflow operation returned false")
                    if node.get("wait_for"):
                        result = await subscriptions[node["wait_for"]].get(node.get("timeout_s"))
                    if node.get("emit"):
                        self.events.publish(node["emit"], result)
                    current = node.get("next")
                except Exception:
                    if not node.get("on_error"):
                        raise
                    current = node["on_error"]
                await asyncio.sleep(0)
            return result
        finally:
            for sub in subscriptions.values():
                sub.close()
