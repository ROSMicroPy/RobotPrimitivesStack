from rpstack.shell.support import require_node

# Stop node services while leaving shell and HTTP control access available.
async def run(context, arguments):
    await require_node(context).stop()
    print('Node stopped; shell and HTTP remain available')
