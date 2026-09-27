from rpstack.shell.support import split_arguments
from rpstack.support import asyncio
import network

# Dispatch Wi-Fi station and access-point status, activation, scan, and connection commands.
async def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) == 0:
        print ("Usage:")
        print ("wifi status - prints wifi client status")
        print ("wifi on - activate wifi client")
        print ("wifi off - deactivate wifi client")
        print ("wifi scan - list visible networks")
        print ("wifi connect <SSID> <PSK> - connect to network")
        print ("wifi ap - prints Access Point status")
        print ("wifi ap on - activate Access Point")
        print ("wifi ap off - deactivate Access Point")
        return

    sta_if = network.WLAN(network.STA_IF)
    cmd = args[0]
    if cmd == "on":
        sta_if.active(True)
    elif cmd == "off":
        sta_if.active(False)
    elif cmd == "status":
        print ("WiFi is {}".format("Active" if sta_if.active() == True else "Inactive"))
        print ("Status {}".format(sta_if.status()))
        if sta_if.isconnected():
            print ("WiFi connection is {}".format("Established" if sta_if.isconnected() else "Not connected"))
    elif cmd == "scan":
        for net in sta_if.scan():
            print ("SSID\tUnknown\tCHN\tSignal")
            print ("{}\t{}\t{}\t{}\t".format(net[0], net[1], net[2], net[3]))
    elif cmd == "connect":
        print ("Connecting to {}".format(args[1]))
        sta_if.connect(args[1], args[2])
        while not sta_if.isconnected():
            await asyncio.sleep(0.05)
        print ("Connected")
    elif cmd == "ap":
        ap_if = network.WLAN(network.AP_IF)
        cmd = args[1]
        if cmd == "on":
            ap_if.active(True)
        elif cmd == "off":
            ap_if.active(False)
        else:
            print ("Access point is {}".format("Active" if ap_if.active() == True else "Inactive"))
