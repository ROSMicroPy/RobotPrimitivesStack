from rpstack.shell.support import split_arguments
import os


# Resolve directory destination behavior and rename the source path.
def run(context, arguments):
    args = split_arguments(arguments)
    path = args[0]
    path2 = args[1]
    src_name = args[0].split("/")[-1]

    try:
        os.listdir(path2)
        path2 += "/" + src_name
    except OSError:
        pass
    print ("renaming {} to {}".format(path, path2))
    os.rename(path, path2)
