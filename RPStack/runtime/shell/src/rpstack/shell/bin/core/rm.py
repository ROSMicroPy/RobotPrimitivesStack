from rpstack.execution_engine import asyncio
from rpstack.shell.support import entries
import os


def _is_dir(path):
	return (os.stat(path)[0] & 0x4000) != 0


def _join_path(parent, child):
	if parent == "/":
		return "/" + child
	if parent.endswith("/"):
		return parent + child
	return parent + "/" + child


async def _remove_path(path):
	if _is_dir(path):
		for entry in entries(path):
			await _remove_path(_join_path(path, entry[0]))
		os.rmdir(path)
	else:
		os.remove(path)
		await asyncio.sleep(0)


async def __main__(args):
	if len(args) < 3:
		print("Usage: rm <path>")
		return

	await _remove_path(args[2])


async def run(context, arguments):
    from rpstack.shell.support import split_arguments
    return await __main__(["python", __name__] + split_arguments(arguments))
