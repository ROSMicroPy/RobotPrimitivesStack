from rpstack.shell import async_shell


def __main__(args):
    node = async_shell.current_node
    if node is None or len(args) < 3:
        raise ValueError("kill requires an active node and task ID")
    task_id = int(args[2])
    if node.tasks.records[task_id]["kind"] not in ("operation", "flow"):
        raise ValueError("use node stop for services")
    node.tasks.spawn("shell:kill", node.tasks.cancel, task_id, kind="command")
