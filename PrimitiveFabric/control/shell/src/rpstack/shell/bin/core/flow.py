from rpstack.shell.support import require_node

# Start a named node workflow and print its managed task ID.
def run(context, arguments):
    print('Task {}'.format(require_node(context).start_flow(arguments.strip())))
