from rpstack.shell.support import require_node, json

async def run(context, arguments):
    await require_node(context).stop()
    print('Node stopped; shell and HTTP remain available')
