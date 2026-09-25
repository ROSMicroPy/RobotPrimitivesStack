import os
from rpstack.shell.support import split_arguments

# Change the working directory, defaulting to the filesystem root.
def run(context, arguments):
    args = split_arguments(arguments)
    os.chdir(args[0] if args else '/')
