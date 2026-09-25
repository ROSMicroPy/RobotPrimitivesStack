import os
from rpstack.shell.support import split_arguments

# Print the shell's current working directory.
def run(context, arguments):
    args = split_arguments(arguments)
    print(os.getcwd())
