from rpstack.shell.support import split_arguments
FOREGROUND_ONLY = True

import sys


# Find an installed mini-commander package under either supported import name.
def _import_module():
    for module_name in ("mp_mini_commander", "mini_commander"):
        try:
            return __import__(module_name)
        except ImportError:
            pass
    return None


# Launch the available terminal file manager and display launch failures.
def run(context, arguments):
    args = split_arguments(arguments)
    module = _import_module()
    if module is None:
        print("Unable to import mp_mini_commander or mini_commander")
        return

    try:
        if hasattr(module, "run"):
            module.run()
        elif hasattr(module, "main"):
            module.main()
        else:
            print("mini commander package has no run() or main()")
    except Exception as exc:
        print("Error running mini commander")
        sys.print_exception(exc)
