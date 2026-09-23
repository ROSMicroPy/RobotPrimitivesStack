from rpstack.shell.support import require_node, json

def run(context, arguments):
    print('Task {}'.format(require_node(context).start_flow(arguments.strip())))
