import os
from somatic_mesh.shell.support import split_arguments

# Change the working directory, defaulting to the filesystem root.
def run(context, arguments):
    args = split_arguments(arguments)
    os.chdir(args[0] if args else '/')
