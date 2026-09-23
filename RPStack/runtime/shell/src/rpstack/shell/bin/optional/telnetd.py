FOREGROUND_ONLY = True

def run(context, arguments):
    from rpstack.shell import utelnetserver
    utelnetserver.start()
    
