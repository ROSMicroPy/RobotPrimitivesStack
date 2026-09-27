from rpstack.shell.support import split_arguments
from rpstack.support import asyncio
# blink.py

__version__ = '1.0.0' # Major.Minor.Patch

import machine


# Toggle a chosen GPIO for the requested number of timed on/off cycles.
async def run(context, arguments):
    args = split_arguments(arguments)
    num = 10
    pin=2
    if len(args) > 0:
        pin = int(args[0])
    if len(args) > 1:
        num = int(args[1])
    ton = 1.0
    if len(args) > 2:
        ton = float(args[2])
    toff = 1.0
    if len(args) > 3:
        toff = float(args[3])

    if not num:
        num = 10

    print("blink pin{} loop{} ondelay{} offdelay{}".format(pin, num, ton, toff))
    led = machine.Pin(pin, machine.Pin.OUT)

    while num>0:
        led.value(1)
        await asyncio.sleep(ton)
        led.value(0)
        await asyncio.sleep(toff)
        num=num-1
