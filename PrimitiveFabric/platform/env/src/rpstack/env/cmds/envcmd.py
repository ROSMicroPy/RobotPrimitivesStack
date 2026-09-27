
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
from rpstack.env import printEnv



class EnvCommand:
    name = "env"

    # Print environment variables without modifying memory or persistent storage.
    def run(self, args):
        # The env command is intentionally read-only: it prints the current
        # environment without modifying persistence or shell state.
        printEnv()
