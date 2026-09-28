# Display the value returned by the platform clock as the command's uptime reading.
def run(context, arguments):
    import time

    print ("Current time from system startup is: {}".format(time.time()))
