import sys


def _import_module():
    for module_name in ("mp_uemacs", "uemacs"):
        try:
            return __import__(module_name)
        except ImportError:
            pass
    return None


def __main__(args):
    module = _import_module()
    if module is None:
        print("Unable to import mp_uemacs or uemacs")
        return

    filename = args[2] if len(args) > 2 else None

    try:
        if hasattr(module, "run"):
            module.run(filename)
        elif hasattr(module, "main"):
            argv = [args[0]]
            if filename is not None:
                argv.append(filename)
            module.main(argv)
        else:
            print("uemacs package has no run() or main()")
    except Exception as exc:
        print("Error running editor")
        sys.print_exception(exc)
