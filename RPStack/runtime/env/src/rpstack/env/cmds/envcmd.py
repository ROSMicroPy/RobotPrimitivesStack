
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
try:
    from rpstack.env import printEnv
except ImportError:
    from envstore import printEnv

try:
    from rpstack.shell import ExternalCommand
except ImportError:
    # Minimal fallback keeps the module importable outside the shell runtime.
    class ExternalCommand:
        name = None

        def run(self, args):
            raise NotImplementedError()


class EnvCommand(ExternalCommand):
    name = "env"

    def run(self, args):
        # The env command is intentionally read-only: it prints the current
        # environment without modifying persistence or shell state.
        printEnv()
