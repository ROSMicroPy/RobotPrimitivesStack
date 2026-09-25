import os
from rpstack.shell.support import split_arguments

# Create a missing file and refresh its timestamp when the filesystem supports it.
def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) != 1:
        raise ValueError('usage: touch PATH')
    with open(args[0], 'a'):
        pass
    if hasattr(os, 'utime'):
        os.utime(args[0], None)
