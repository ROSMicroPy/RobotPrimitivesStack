from rpstack.shell.support import split_arguments
from rpstack.shell.support import entries
from rpstack.shell.support import human
import os


# Print filesystem usage for the root and detected mount points.
def run(context, arguments):
    args = split_arguments(arguments)
    _print_mount_stats("/")

    for pt in entries("/"):
        f = pt[0]
        if len(pt) == 3:#Currently means vfs mount point
            print ("")
            _print_mount_stats("/"+f)

# Convert filesystem block statistics into used/free byte counts for display.
def _print_mount_stats(path):
    info = os.statvfs(path)
    block_size = info[0]
    fragment_size = info[1]
    fragment_count = info[2]
    free_block_count = info[3]

    print ("Filesystem '{}' {}-blocks       total {}    free {}".format(path, block_size, fragment_count, free_block_count))
    used = (fragment_count - free_block_count) * block_size
    free = free_block_count * block_size
    print ("        USED {} bytes   {}".format(used, human(used)))
    print ("        FREE {} bytes   {}".format(free, human(free)))
