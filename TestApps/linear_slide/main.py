"""VL53L4CD-observed linear slide with a manifest-driven REST API."""

try:
    import ujson as json
except ImportError:
    import json

import wifi
from machine import I2C, Pin

from rpstack.linear_slide import LinearSlide
from rpstack.micropyserver import ManifestRestApi, MicroPyServer


ENABLE_PIN = 21
STEP_PIN = 17
DIR_PIN = 3
I2C_SDA_PIN = 5
I2C_SCL_PIN = 4
POSITIVE_DIRECTION = True
MANIFEST_PATH = "/lib/linear_slide_manifest.json"
SERVER_PORT = 80


def load_manifest(path=MANIFEST_PATH):
    with open(path, "r") as manifest_file:
        return json.loads(manifest_file.read())


def create_slide():
    i2c = I2C(0, sda=Pin(I2C_SDA_PIN), scl=Pin(I2C_SCL_PIN))
    return LinearSlide(
        i2c,
        step_pin=STEP_PIN,
        dir_pin=DIR_PIN,
        enable_pin=ENABLE_PIN,
        positive_direction=POSITIVE_DIRECTION,
        tolerance_mm=1,
        max_steps=10000,
    )


def main():
    wifi.connect_wifi()
    slide = create_slide()
    server = MicroPyServer(port=SERVER_PORT)
    ManifestRestApi(server, load_manifest(), slide)

    slide.start()
    print("Linear slide REST API ready on port {}".format(SERVER_PORT))
    print("Manifest: GET /manifest")
    try:
        server.start()
    finally:
        server.stop()
        slide.shutdown()


if __name__ == "__main__":
    main()
