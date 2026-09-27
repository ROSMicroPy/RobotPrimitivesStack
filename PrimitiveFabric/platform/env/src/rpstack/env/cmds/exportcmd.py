
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
from rpstack.env import setEnv



# Parse joined or tokenized assignments and distinguish session-only from persistent exports.
def _parse_export_args(args):
    # Accept either `export NAME=value` or tokenized forms such as
    # `export NAME = value` and `export NAME != value`.
    if len(args) < 2:
        raise ValueError("Usage: export NAME[!]=VALUE")

    tokens = list(args[1:])
    first = tokens.pop(0)
    name = None
    operator = None
    value = ""

    if "!=" in first:
        name, value = first.split("!=", 1)
        operator = "!="
    elif "=" in first:
        name, value = first.split("=", 1)
        operator = "="
    else:
        name = first
        if not tokens:
            raise ValueError("Usage: export NAME [!]= VALUE")
        operator = tokens.pop(0)
        if operator not in ("=", "!="):
            raise ValueError("Usage: export NAME [!]= VALUE")
        value = " ".join(tokens)
        return name, operator, value

    if tokens:
        suffix = " ".join(tokens)
        if value:
            value = value + " " + suffix
        else:
            value = suffix

    return name, operator, value


class ExportCommand:
    name = "export"

    # Apply a parsed export assignment and display invalid-input errors to the shell user.
    def run(self, args):
        try:
            name, operator, value = _parse_export_args(args)
            # `!=` marks the variable as persistent on disk, while `=` keeps
            # it in-memory for the current session only.
            setEnv(name, value, operator == "!=")
        except Exception as exc:
            print(str(exc))
