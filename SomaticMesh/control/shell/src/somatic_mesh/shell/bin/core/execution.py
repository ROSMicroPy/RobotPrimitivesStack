from somatic_mesh.shell.support import require_node

# Display local and remote execution diagnostics from the active node.
def run(context, arguments):
    print(require_node(context).execution_status())
