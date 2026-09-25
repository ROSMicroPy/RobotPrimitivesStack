from rpstack.shell.support import split_arguments
import os


# Print firmware system, release, version, and machine information.
def run(context, arguments):
    args = split_arguments(arguments)
    uname = os.uname()
    print ("System {} release {} version {}".format(uname.sysname, uname.release, uname.version))
    print ("Machine type {}".format(uname.machine))
