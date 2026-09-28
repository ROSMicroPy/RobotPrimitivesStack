# Request an immediate device reset through the machine interface.
def run(context, arguments):
    import machine
    machine.reset()
