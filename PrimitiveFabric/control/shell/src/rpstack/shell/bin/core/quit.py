# Ask the current shell context to stop accepting input.
def run(context, arguments):
    context.request_exit()
