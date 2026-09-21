
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
from .bootmgr import run as _run
import mip
import sys

_BOOTSTRAP_IMPORT = "import rpstack.bootmgr as bootmgr"
_BOOTSTRAP_RUN = "bootmgr.run()"
_DEFAULT_APP_URLS = (
    "https://gitlab.com/robot-primitives/micropython_modules/mp_mini_commander/-/raw/main/py/package.json",
    "https://gitlab.com/robot-primitives/micropython_modules/ide/mp_git/-/raw/main/package.json",
    "https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/archdef/RPStack/runtime/shell/package.json",
    "https://gitlab.com/robot-primitives/micropython_modules/mp_uemacs/-/raw/main/py/package.json",
)


def run():
    try:
        _run()
    except Exception as exc:
        if hasattr(sys, "print_exception"):
            sys.print_exception(exc)
        else:
            raise


def bootstrap(filename="main.py"):
    try:
        with open(filename, "r") as handle:
            source = handle.read()
    except OSError:
        source = ""
        with open(filename, "w") as handle:
            handle.write("")

    if _BOOTSTRAP_IMPORT in source and _BOOTSTRAP_RUN in source:
        install_default_apps()
        return

    if source and not source.endswith("\n"):
        source += "\n"

    lines = []
    if _BOOTSTRAP_IMPORT not in source:
        lines.append(_BOOTSTRAP_IMPORT)
    if _BOOTSTRAP_RUN not in source:
        lines.append(_BOOTSTRAP_RUN)

    if not lines:
        return

    with open(filename, "w") as handle:
        handle.write(source + "\n".join(lines) + "\n")
    
    install_default_apps()

def install_default_apps():
    for url in _DEFAULT_APP_URLS:
        mip.install(url)
