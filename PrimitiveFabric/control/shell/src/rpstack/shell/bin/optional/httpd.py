FOREGROUND_ONLY = True

# Start the standalone file server serving files from /www on port 80.
def run(context, arguments):
    from rpstack.shell.microWebSrv import MicroWebSrv

    mws = MicroWebSrv(routeHandlers=[], port=80, bindIP='0.0.0.0', webPath="/www")
    mws.Start(threaded=True)

