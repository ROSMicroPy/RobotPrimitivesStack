from rpstack.shell.support import require_node

# Reconstruct node services and report readiness after reset completes.
async def run(context, arguments):
    await require_node(context).reset()
    print('Node ready')
