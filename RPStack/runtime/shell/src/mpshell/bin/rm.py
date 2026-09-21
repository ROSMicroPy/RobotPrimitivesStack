import os


def _is_dir(path):
	return (os.stat(path)[0] & 0x4000) != 0


def _join_path(parent, child):
	if parent == "/":
		return "/" + child
	if parent.endswith("/"):
		return parent + child
	return parent + "/" + child


def _remove_path(path):
	if _is_dir(path):
		for entry in os.ilistdir(path):
			_remove_path(_join_path(path, entry[0]))
		os.rmdir(path)
	else:
		os.remove(path)


def __main__(args):
	if len(args) < 3:
		print("Usage: rm <path>")
		return

	_remove_path(args[2])
