from rpstack.shell.support import require_node, json

def run(context, arguments):
    print(require_node(context).execution_status())
