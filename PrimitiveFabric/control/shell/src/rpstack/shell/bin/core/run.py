from rpstack.shell.support import require_node, json

# Parse service, operation, and optional JSON arguments before submitting managed work.
def run(context, arguments):
    parts = arguments.split(None, 2)
    if len(parts) < 2:
        raise ValueError('usage: run SERVICE OPERATION [JSON]')
    values = json.loads(parts[2]) if len(parts) > 2 else {}
    print('Task {}'.format(require_node(context).submit(parts[0], parts[1], values)))
