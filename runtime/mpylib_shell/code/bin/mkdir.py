import os


def __main__(args):
	if len(args) < 3:
		print("Usage: mkdir <path>")
		return

	path = args[2]
	print("creating dir {}".format(path))
	os.mkdir(path)
