import os
from rpstack.shell.support import split_arguments

def run(context, arguments):
    args = split_arguments(arguments)
    print(os.getcwd())
