# Print MicroPython's memory allocation diagnostics.
def run(context, arguments):
    import micropython
    micropython.mem_info()
