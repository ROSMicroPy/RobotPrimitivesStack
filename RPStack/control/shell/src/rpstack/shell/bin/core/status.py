from rpstack.shell.support import require_node

# Print the active node's lifecycle state.
def run(context, arguments):
    print(require_node(context).state)
