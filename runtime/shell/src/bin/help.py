from mpshell.sh import get_bins, cmds_integrated
from mpshell import registry


def __main__(args):
	print ("Available commands:")
	for k in cmds_integrated:
		print ("{}".format(k))
	
	print ("")
	print ("Available bins:")
	pybins, shbins = get_bins()
	for k in pybins:
		print ("{}".format(k))
	for k in shbins:
		print ("{}".format(k))
	print ("")
	print ("Available external commands:")
	for entry in registry.read_ext_registry():
		try:
			loaded = registry.load_external_command(entry)
			print ("{}".format(loaded["name"]))
		except Exception:
			class_name = entry.get("class", "?")
			path = entry.get("path", "?")
			print ("{} (failed to load from {})".format(class_name, path))
	print ("")
