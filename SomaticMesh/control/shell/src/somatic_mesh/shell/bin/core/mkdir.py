import os
from somatic_mesh.shell.support import split_arguments

# Require one path and create the requested directory.
def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) != 1:
        raise ValueError('usage: mkdir PATH')
    os.mkdir(args[0])
