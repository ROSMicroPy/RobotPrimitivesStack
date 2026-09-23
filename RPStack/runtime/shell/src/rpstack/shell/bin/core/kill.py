from rpstack.shell.support import require_node, json

async def run(context, arguments):
    node = require_node(context)
    task_id = int(arguments.strip())
    if node.tasks.records[task_id]['kind'] not in ('operation', 'flow'):
        raise ValueError('use stop to stop services')
    await node.tasks.cancel(task_id)
