from rpstack.shell.support import split_arguments
from rpstack.support import asyncio
from rpstack.shell.support import entries
import os

try:
    import re
except ImportError:
    import ure as re


# Read the filesystem mode to distinguish directories from files.
def _is_dir(path):
    return (os.stat(path)[0] & 0x4000) != 0


# Check path existence, treating stat failures as missing paths.
def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


# Join directory and child names without duplicating root separators.
def _join_path(parent, child):
    if parent == "/":
        return "/" + child
    if parent.endswith("/"):
        return parent + child
    return parent + "/" + child


# Extract the last path component while tolerating a trailing slash.
def _basename(path):
    trimmed = path[:-1] if path.endswith("/") and path != "/" else path
    if trimmed == "/":
        return "/"
    return trimmed.split("/")[-1]


# Separate the search directory from the filename regular expression.
def _split_source_pattern(source):
    trimmed = source[:-1] if source.endswith("/") and source != "/" else source
    idx = trimmed.rfind("/")
    if idx < 0:
        return os.getcwd(), trimmed
    if idx == 0:
        return "/", trimmed[1:]
    return trimmed[:idx], trimmed[idx + 1:]


# Use an existing literal path or expand a regex against sorted directory entries.
def _expand_sources(source):
    if _exists(source):
        return [source]

    parent, pattern = _split_source_pattern(source)
    if not pattern:
        return []

    try:
        matcher = re.compile(pattern)
    except Exception as err:
        print("Invalid regex {}: {}".format(source, err))
        return None

    try:
        items = os.listdir(parent)
    except OSError:
        return []

    matches = []
    for name in sorted(items):
        if matcher.match(name):
            matches.append(_join_path(parent, name))
    return matches


# Copy binary contents in small chunks, yielding between writes.
async def _copy_file(src, dst):
    with open(src, "rb") as src_handle:
        with open(dst, "wb") as dst_handle:
            while True:
                chunk = src_handle.read(512)
                if not chunk:
                    break
                dst_handle.write(chunk)
                await asyncio.sleep(0)


# Recursively create destination directories and copy their contents.
async def _copy_dir(src, dst):
    if not _exists(dst):
        os.mkdir(dst)
    for entry in entries(src):
        name = entry[0]
        src_child = _join_path(src, name)
        dst_child = _join_path(dst, name)
        if _is_dir(src_child):
            await _copy_dir(src_child, dst_child)
        else:
            await _copy_file(src_child, dst_child)


# Place the source inside an existing destination directory when appropriate.
def _resolve_destination(src, dest):
    if _exists(dest) and _is_dir(dest):
        return _join_path(dest, _basename(src))
    return dest


# Resolve destination semantics and dispatch to file or recursive directory copying.
async def _copy_path(src, dest):
    dst = _resolve_destination(src, dest)
    if _is_dir(src):
        await _copy_dir(src, dst)
    else:
        await _copy_file(src, dst)


# Validate copy arguments, expand source matches, and copy each selected path.
async def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) < 2:
        print("Usage: cp <source-regex-or-path> <destination>")
        return

    source = args[0]
    dest = args[1]
    sources = _expand_sources(source)
    if sources is None:
        return
    if not sources:
        print("cp: no matches for {}".format(source))
        return

    if len(sources) > 1 and (not _exists(dest) or not _is_dir(dest)):
        print("cp: destination must be an existing directory when copying multiple sources")
        return

    for src in sources:
        await _copy_path(src, dest)
