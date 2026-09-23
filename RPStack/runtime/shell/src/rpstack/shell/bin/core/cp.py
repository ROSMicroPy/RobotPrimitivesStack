from rpstack.execution_engine import asyncio
from rpstack.shell.support import entries
import os

try:
	import re
except ImportError:
	import ure as re


def _is_dir(path):
	return (os.stat(path)[0] & 0x4000) != 0


def _exists(path):
	try:
		os.stat(path)
		return True
	except OSError:
		return False


def _join_path(parent, child):
	if parent == "/":
		return "/" + child
	if parent.endswith("/"):
		return parent + child
	return parent + "/" + child


def _basename(path):
	trimmed = path[:-1] if path.endswith("/") and path != "/" else path
	if trimmed == "/":
		return "/"
	return trimmed.split("/")[-1]


def _split_source_pattern(source):
	trimmed = source[:-1] if source.endswith("/") and source != "/" else source
	idx = trimmed.rfind("/")
	if idx < 0:
		return os.getcwd(), trimmed
	if idx == 0:
		return "/", trimmed[1:]
	return trimmed[:idx], trimmed[idx + 1:]


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


async def _copy_file(src, dst):
	with open(src, "rb") as src_handle:
		with open(dst, "wb") as dst_handle:
			while True:
				chunk = src_handle.read(512)
				if not chunk:
					break
				dst_handle.write(chunk)
				await asyncio.sleep(0)


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


def _resolve_destination(src, dest):
	if _exists(dest) and _is_dir(dest):
		return _join_path(dest, _basename(src))
	return dest


async def _copy_path(src, dest):
	dst = _resolve_destination(src, dest)
	if _is_dir(src):
		await _copy_dir(src, dst)
	else:
		await _copy_file(src, dst)


async def __main__(args):
	if len(args) < 4:
		print("Usage: cp <source-regex-or-path> <destination>")
		return

	source = args[2]
	dest = args[3]
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


async def run(context, arguments):
    from rpstack.shell.support import split_arguments
    return await __main__(["python", __name__] + split_arguments(arguments))
