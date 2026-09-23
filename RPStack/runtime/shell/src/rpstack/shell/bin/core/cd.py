import os
from rpstack.shell.support import split_arguments

def run(context, arguments):
    args = split_arguments(arguments)
    os.chdir(args[0] if args else '/')
