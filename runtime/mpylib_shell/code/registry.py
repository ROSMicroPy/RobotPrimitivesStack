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

    def run(self, args):
        raise NotImplementedError()


def set_refresh_handler(handler):
    global _refresh_handler
    _refresh_handler = handler


def module_name_from_path(path):
    name = path.rsplit("/", 1)[-1]
    if name.endswith(".py"):
        name = name[:-3]
    return name


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


def ensure_ext_registry():
    mkdir_p("/lib")
    mkdir_p("/lib/etc")
    mkdir_p("/lib/etc/mpshell")
    try:
        os.stat(EXT_COMMANDS_FILE)
    except OSError:
        with open(EXT_COMMANDS_FILE, "w") as f:
            json.dump([], f)


def read_ext_registry():
    try:
        ensure_ext_registry()
        with open(EXT_COMMANDS_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def write_ext_registry(entries):
    ensure_ext_registry()
    with open(EXT_COMMANDS_FILE, "w") as f:
        json.dump(entries, f)


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


def import_module_from_path(path):
    module_dir = path.rsplit("/", 1)[0] if "/" in path else ""
    module_name = module_name_from_path(path)
    added_path = False
    if module_dir and module_dir not in sys.path:
        sys.path.append(module_dir)
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


def command_name_for_instance(instance, class_name):
    if hasattr(instance, "name") and instance.name:
        return instance.name
    return class_name.lower()


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
