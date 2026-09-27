# Send terminal escape sequences to clear the display and reset the cursor.
def run(context, arguments):
    print ("\033[2J")
    print ("\033[0;0H")

