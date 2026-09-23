import os
from rpstack.shell.support import split_arguments

def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) != 1:
        raise ValueError('usage: mkdir PATH')
    os.mkdir(args[0])
