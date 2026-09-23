import os
from rpstack.shell.support import split_arguments

def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) != 1:
        raise ValueError('usage: rmdir PATH')
    os.rmdir(args[0])
