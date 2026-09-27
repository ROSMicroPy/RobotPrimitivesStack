FOREGROUND_ONLY = True

# Start the device telnet server and its remote terminal interface.
def run(context, arguments):
    from rpstack.shell import utelnetserver
    utelnetserver.start()

