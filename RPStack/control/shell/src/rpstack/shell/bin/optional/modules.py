# Print the interpreter's currently loaded module table.
def run(context, arguments):
    import sys
    print(sys.modules)
