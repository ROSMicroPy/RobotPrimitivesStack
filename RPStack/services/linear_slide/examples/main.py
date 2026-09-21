"""Example LinearSlide application. Update GPIO pins for the target board."""

from machine import I2C, Pin

from rpstack.linear_slide import LinearSlide


ENABLE_PIN = 21
STEP_PIN = 17
DIR_PIN = 3
I2C_SDA_PIN = 5
I2C_SCL_PIN = 4
TARGET_POSITION_MM = 100


def main():
    i2c = I2C(0, sda=Pin(I2C_SDA_PIN), scl=Pin(I2C_SCL_PIN))
    with LinearSlide(
        i2c,
        step_pin=STEP_PIN,
        dir_pin=DIR_PIN,
        enable_pin=ENABLE_PIN,
        tolerance_mm=1,
        max_steps=10000,
    ) as slide:
        print("Starting position: {} mm".format(slide.getPosition()))
        final_position = slide.gotoPosition(TARGET_POSITION_MM)
        print("Final position: {} mm".format(final_position))


if __name__ == "__main__":
    main()
