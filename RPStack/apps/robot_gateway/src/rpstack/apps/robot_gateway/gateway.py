"""Robot composition REST gateway, mounted on the node's shared HTTP server."""
from rpstack.support import asyncio
from rpstack.micropyserver.http import send_json


class GatewayApp:
    # Remember the HTTP and catalog dependencies whose public views this gateway will expose.
    def __init__(self, node, http='http', catalog='catalog'):
        self.node, self.http_id, self.catalog_id = node, http, catalog
        self.server = None
        self.routes = []

    # Resolve runtime dependencies and register discovery routes, rejecting collisions with
    # existing handlers.
    async def start(self):
        self.catalog = self.node.runtime_instances[self.catalog_id]
        self.server = self.node.runtime_instances[self.http_id].server
        handlers = {'/api/robot': self.robot,
                    '/api/robot/status': self.status,
                    '/api/robot/messages': self.messages,
                    '/health': self.health}
        if any(path in handlers for method, path, handler in self.server.routes):
            raise ValueError('gateway route already registered')
        for path, handler in handlers.items():
            self.server.add_route(path, handler, 'GET')
            self.routes.append(('GET', path, handler))

    # Return the catalog's current robot-wide discovery snapshot.
    async def robot(self, request, response):
        send_json(response, self.catalog.snapshot())

    # Report node health, signal/catalog counters, and the number of known nodes.
    async def status(self, request, response):
        send_json(response, {'entity': self.node.signals.entity, 'node_id': self.node.signals.node_id,
            'state': self.node.state, 'signals': dict(self.node.signals.stats),
            'catalog': dict(self.catalog.stats), 'known_nodes': self.catalog.snapshot()['count']})

    # Return retained messages without consuming them, allowing multiple observers.
    async def messages(self, request, response):
        # Non-destructive so multiple Architect clients and gateways can observe concurrently.
        send_json(response, {'messages': list(self.catalog.messages)})

    # Return the gateway's fixed identity and health response.
    async def health(self, request, response):
        send_json(response, {'status': 'ok', 'service': 'robot_gateway', 'version': '1.0.0'})

    # Keep the app resident while the HTTP server dispatches its handlers.
    async def run(self):
        await asyncio.Event().wait()

    # Remove only the HTTP routes installed by this gateway instance.
    async def stop(self):
        if self.server:
            for route in self.routes:
                if route in self.server.routes:
                    self.server.routes.remove(route)
        self.routes = []
