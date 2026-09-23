from rpstack.execution_engine import asyncio
# blink.py

__version__ = '1.0.0' # Major.Minor.Patch

from rpstack.shell.support import human
import os
import machine
import time


async def __main__(args):
	num = 10
	pin=2
	if len(args) > 2:
		pin = int(args[2])
	if len(args) > 3:
		num = int(args[3])
	ton = 1.0
	if len(args) > 4:
		ton = float(args[4])
	toff = 1.0
	if len(args) > 5:
		toff = float(args[5])
	
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



async def run(context, arguments):
    from rpstack.shell.support import split_arguments
    return await __main__(["python", __name__] + split_arguments(arguments))
