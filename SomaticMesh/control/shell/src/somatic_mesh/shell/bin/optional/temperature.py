# Convert the ESP32's raw Fahrenheit temperature reading to Celsius for display.
def run(context, arguments):
    import esp32

    raw_t = esp32.raw_temperature()
    t = (raw_t - 32) / 1.8

    print ("{} Deg Celsius".format(t))

