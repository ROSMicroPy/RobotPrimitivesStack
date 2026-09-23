import os


def __main__(args):
	uname = os.uname()
	print ("System {} release {} version {}".format(uname.sysname, uname.release, uname.version))
	print ("Machine type {}".format(uname.machine))



def run(context, arguments):
    from rpstack.shell.support import split_arguments
    return __main__(["python", __name__] + split_arguments(arguments))
