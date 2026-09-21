
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
print("Registering env commands")

from mpenv import loadPersistent
import mpshell


# Load persisted variables before registering commands so shell usage sees
# the restored environment immediately after startup.
loadPersistent()

_COMMANDS = (
    ("/lib/mpenv/cmds/exportcmd.py", "ExportCommand"),
    ("/lib/mpenv/cmds/envcmd.py", "EnvCommand"),
)

# Register each command module with mp_shell's external command registry.
for path, class_name in _COMMANDS:
    mpshell.registercommand(path, class_name)
