from rpstack.shell.support import split_arguments
from rpstack.support import asyncio
from rpstack.shell.support import entries
import os


# Use filesystem mode bits to distinguish a directory from a file.
def _is_dir(path):
    return (os.stat(path)[0] & 0x4000) != 0


# Join parent and child paths while handling root separators.
def _join_path(parent, child):
    if parent == "/":
        return "/" + child
    if parent.endswith("/"):
        return parent + child
    return parent + "/" + child


# Remove directory contents recursively, yielding after individual file deletions.
async def _remove_path(path):
    if _is_dir(path):
        for entry in entries(path):
            await _remove_path(_join_path(path, entry[0]))
        os.rmdir(path)
    else:
        os.remove(path)
        await asyncio.sleep(0)


# Require a path and dispatch its recursive removal.
async def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) < 1:
        print("Usage: rm <path>")
        return

    await _remove_path(args[0])
