from rpstack.shell import async_shell


def __main__(args):
    if async_shell.current_node is None:
        print("No node runtime is active")
        return
    async_shell.print_tasks(async_shell.current_node)
