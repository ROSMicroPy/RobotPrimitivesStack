import os
from rpstack.shell.support import split_arguments

def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) != 1:
        raise ValueError('usage: touch PATH')
    with open(args[0], 'a'):
        pass
    if hasattr(os, 'utime'):
        os.utime(args[0], None)
