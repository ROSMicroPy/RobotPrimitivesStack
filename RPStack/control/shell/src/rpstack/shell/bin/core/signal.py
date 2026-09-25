from rpstack.shell.support import require_node, json

# Parse an optional JSON payload and publish a named application signal.
def run(context, arguments):
    parts = arguments.split(None, 1)
    if not parts:
        raise ValueError('usage: signal NAME [JSON]')
    payload = json.loads(parts[1]) if len(parts) > 1 else None
    require_node(context).publish_signal(parts[0], payload)
