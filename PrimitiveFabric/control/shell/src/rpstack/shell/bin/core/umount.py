from rpstack.shell.support import split_arguments
import uos
from rpstack.shell.support import vfses as _vfses
import gc

# Unmount a filesystem and release tracked RAM-disk ownership when applicable.
def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) < 1:
        print ("Usage:")
        print ("umount <path>")
        print ("umount /ram0")
        return
    path = args[0]
    if path in _vfses:
        vfs, bdev = _vfses[path]
        uos.umount(vfs)
        del _vfses[path]
        gc.collect()
    else:
        uos.umount(args[0])
