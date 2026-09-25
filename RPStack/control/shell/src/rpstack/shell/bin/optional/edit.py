from rpstack.shell.support import split_arguments
FOREGROUND_ONLY = True

import sys


# Try supported editor package names and return the first installed implementation.
def _import_module():
    for module_name in ("mp_uemacs", "uemacs"):
        try:
            return __import__(module_name)
        except ImportError:
            pass
    return None


# Launch the available editor on an optional file, reporting unsupported entry points or
# failures.
def run(context, arguments):
    args = split_arguments(arguments)
    module = _import_module()
    if module is None:
        print("Unable to import mp_uemacs or uemacs")
        return

    filename = args[0] if len(args) > 0 else None

    try:
        if hasattr(module, "run"):
            module.run(filename)
        elif hasattr(module, "main"):
            argv = ['edit']
            if filename is not None:
                argv.append(filename)
            module.main(argv)
        else:
            print("uemacs package has no run() or main()")
    except Exception as exc:
        print("Error running editor")
        sys.print_exception(exc)
