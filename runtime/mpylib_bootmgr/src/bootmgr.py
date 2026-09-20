
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
"""Boot loader for init.d scripts compatible with MicroPython."""

import os
import sys


def _is_init_script(name):
    if len(name) < 7 or name[0] != "S" or not name.endswith(".py"):
        return False

    order_end = 1
    name_len = len(name)
    while order_end < name_len and name[order_end].isdigit():
        order_end += 1

    return order_end > 2 and name[order_end:order_end + 1] == "_"


def _dirname(path):
    if not path:
        return ""
    slash = path.rfind("/")
    if slash < 0:
        return ""
    if slash == 0:
        return "/"
    return path[:slash]


def _join_path(base, name):
    if not base or base == ".":
        return name
    if base == "/":
        return "/" + name
    return base + "/" + name


def _resolve_init_dir():
    boot_dir = _dirname(globals().get("__file__", ""))
    candidates = []

    if boot_dir:
        parent_dir = _dirname(boot_dir)
        candidates.append(_join_path(parent_dir, "init.d"))
        candidates.append(_join_path(boot_dir, "init.d"))

    candidates.append("/init.d")
    candidates.append("/lib/init.d")
    candidates.append("init.d")

    seen = {}
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen[candidate] = True
            try:
                os.listdir(candidate)
                return candidate
            except OSError:
                pass

    raise OSError("init.d directory not found")


def _load_module(script_name):
    init_dir = _resolve_init_dir()
    module_name = "init_d_" + script_name[:-3].replace("-", "_")
    module_globals = {
        "__name__": module_name,
        "__file__": _join_path(init_dir, script_name),
    }

    with open(module_globals["__file__"], "r") as handle:
        source = handle.read()

    sys.modules[module_name] = module_globals
    exec(compile(source, module_globals["__file__"], "exec"), module_globals)
    return module_globals


def run():
    init_dir = _resolve_init_dir()
    scripts = sorted(name for name in os.listdir(init_dir) if _is_init_script(name))

    for script_name in scripts:
        module = _load_module(script_name)
        runner = module.get("run")
        if runner is not None:
            runner()


if __name__ == "__main__":
    run()
