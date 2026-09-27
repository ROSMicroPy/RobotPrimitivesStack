from rpstack.shell.support import split_arguments
import machine

# Display CPU frequency or apply a requested frequency supplied in MHz.
def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) < 1:
        print ("Current CPU Frequency: {} MHz".format(machine.freq()/1000/1000))
    elif len(args) == 1:
        print ("Setting CPU Frequency to: {} MHz".format(int(args[0])))
        machine.freq(int(args[0])*1000*1000)
