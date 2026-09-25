
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
try:
    import ujson as json
except ImportError:
    import json

import os


ENV_DIR = "/lib/etc/env"
ENV_FILE = ENV_DIR + "/env.json"
_env = {}
_persistent_names = {}


# Build parent directories one component at a time for MicroPython-compatible persistence.
def _mkdir_p(path):
    # MicroPython does not provide a recursive mkdir helper, so build the path
    # one segment at a time and ignore directories that already exist.
    if not path or path == "/":
        return
    current = ""
    for part in path.split("/"):
        if not part:
            if current == "":
                current = "/"
            continue
        if current == "/":
            current = "/" + part
        else:
            current = current + "/" + part
        try:
            os.mkdir(current)
        except OSError:
            pass


# Save only variables explicitly marked persistent to the environment file.
def _write_persistent():
    # Only names explicitly marked persistent are written back to disk.
    _mkdir_p(ENV_DIR)
    data = {}
    for name in sorted(_persistent_names.keys()):
        data[name] = _env.get(name, "")
    with open(ENV_FILE, "w") as handle:
        json.dump(data, handle)


# Replace in-memory environment state with values loaded from persistent storage.
def loadPersistent():
    global _env
    global _persistent_names
    # Reload from disk into fresh dictionaries so startup and manual reloads
    # always reflect the current persisted state.
    _env = {}
    _persistent_names = {}
    try:
        with open(ENV_FILE, "r") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            for name in data:
                value = data[name]
                _env[name] = "" if value is None else str(value)
                _persistent_names[name] = True
    except OSError:
        pass
    except Exception as exc:
        print("Failed to load env vars")
        try:
            import sys
            sys.print_exception(exc)
        except Exception:
            pass


# Return a named environment value or None when it has not been set.
def getEnv(name):
    return _env.get(name)


# Normalize a value to text and update its session-only or persistent status.
def setEnv(name, value, isPersistant=False):
    # Values are normalized to strings so callers see shell-like behavior
    # regardless of the original Python type.
    if not name:
        raise ValueError("Environment variable name is required")
    if value is None:
        value = ""
    value = str(value)
    _env[name] = value
    if isPersistant:
        _persistent_names[name] = True
        _write_persistent()
    elif name in _persistent_names:
        del _persistent_names[name]
        _write_persistent()
    return value


# Return environment name/value pairs in stable sorted order.
def items():
    return sorted(_env.items())


# Print a predictable shell-style view of the current environment.
def printEnv():
    # Emit a stable, sorted view so output is predictable for users and tests.
    for name, value in items():
        print("{}={}".format(name, value))


# Restore persisted variables when the package is imported by startup hooks.
loadPersistent()
