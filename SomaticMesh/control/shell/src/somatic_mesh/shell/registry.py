import os
import sys

try:
    import ujson as json
except:
    import json


EXT_COMMANDS_FILE = "/lib/etc/mpshell/extcmds.json"
_refresh_handler = None


class ExternalCommand:
    name = None

    # Define the execution hook that installed external commands must implement.
    def run(self, args):
        raise NotImplementedError()


# Install the callback used after external command registration changes.
def set_refresh_handler(handler):
    global _refresh_handler
    _refresh_handler = handler


# Derive an import name from a command filename, removing a Python suffix.
def module_name_from_path(path):
    name = path.rsplit("/", 1)[-1]
    if name.endswith(".py"):
        name = name[:-3]
    return name


# Attempt to create every directory component, tolerating already-existing paths and OS errors.
def mkdir_p(path):
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


# Create the registry's parent directories and initialize a missing registry as an empty list.
def ensure_ext_registry():
    mkdir_p(EXT_COMMANDS_FILE.rsplit("/", 1)[0])
    try:
        os.stat(EXT_COMMANDS_FILE)
    except OSError:
        with open(EXT_COMMANDS_FILE, "w") as f:
            json.dump([], f)


# Load external command entries, falling back to an empty registry on invalid data or read
# failure.
def read_ext_registry():
    try:
        with open(EXT_COMMANDS_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


# Ensure the registry exists and replace its serialized entry list.
def write_ext_registry(entries):
    ensure_ext_registry()
    with open(EXT_COMMANDS_FILE, "w") as f:
        json.dump(entries, f)


# Persist a new path/class registration once and notify the refresh callback.
def registercommand(path, class_name):
    entries = read_ext_registry()
    for entry in entries:
        if entry.get("path") == path and entry.get("class") == class_name:
            break
    else:
        entries.append({"path": path, "class": class_name})
        write_ext_registry(entries)
    if _refresh_handler is not None:
        _refresh_handler()


# Temporarily expose the command directory and reload its module from the requested path.
def import_module_from_path(path):
    module_dir = path.rsplit("/", 1)[0] if "/" in path else ""
    module_name = module_name_from_path(path)
    added_path = False
    if module_dir and module_dir not in sys.path:
        sys.path.insert(0, module_dir)
        added_path = True
    try:
        if module_name in sys.modules:
            del sys.modules[module_name]
        return __import__(module_name)
    finally:
        if added_path:
            try:
                sys.path.remove(module_dir)
            except ValueError:
                pass


# Use an explicit command name or derive one from its class name.
def command_name_for_instance(instance, class_name):
    if hasattr(instance, "name") and instance.name:
        return instance.name
    return class_name.lower()


# Import and instantiate a registered command, returning its discovery metadata.
def load_external_command(entry):
    module = import_module_from_path(entry["path"])
    cls = getattr(module, entry["class"])
    instance = cls()
    return {
        "name": command_name_for_instance(instance, entry["class"]),
        "instance": instance,
        "module_name": module_name_from_path(entry["path"]),
        "path": entry["path"],
        "class": entry["class"],
    }
