import os
from rpstack.shell.support import split_arguments

# Require one path and remove the specified empty directory.
def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) != 1:
        raise ValueError('usage: rmdir PATH')
    os.rmdir(args[0])
