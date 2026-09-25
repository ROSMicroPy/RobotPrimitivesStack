# Getting Started

## Run without hardware

Clone the repository and run these commands from its root using Python 3:

```sh
python3 examples/slide_nodes/demo.py
python3 examples/robie1/main.py
```

The first assembles the real slide controller with simulated hardware. The second coordinates a workflow across three simulated nodes and transport links. Neither requires a connected board or a ROS installation.

## Prepare an ESP32 slide device

The slide demo expects MicroPython with `_thread`, `asyncio`, `machine`, `network`, and `espnow`. Install `mpremote` on your workstation. Choose firmware appropriate to your exact board and flash layout.

Review `examples/slide_nodes/node1.device.json` before connecting hardware:

| Setting | Demo default |
| --- | --- |
| I2C bus / SDA / SCL | 0 / 5 / 4 |
| TOF address | 41 (`0x29`) |
| STEP / DIR / ENABLE | 17 / 3 / 21 |
| Pulse delay | 100 µs HIGH + 100 µs LOW |
| Absolute target range | 30–300 mm |
| Maximum commanded steps per target move | 100,000 |
| ESP-NOW channel / entity | 6 / `SlideDemo` |

These are deployment choices, not universal board pin assignments. Calibration moves in both electrical directions; provide clearance for both legs.

## Install the complete package

```sh
cd examples/slide_nodes
mpremote mip install package.json
mpremote repl
```

For a specific connected board, use `mpremote connect /dev/ttyACM0 mip install package.json`. The package installs the launcher, both node manifests, and its local dependencies. It does not replace `main.py`. Reset after installation so imported modules are refreshed. Preserve custom manifest settings before reinstalling.

## Configure gateway networking

Before startup, configure the board's Wi-Fi credentials:

```python
from rpstack.env import setEnv
setEnv('WIFI_SSID', 'your-network', True)
setEnv('WIFI_PASSWORD', 'your-password', True)
```

The access point channel must match the ESP-NOW channel (default 6) in all three
installed manifests. Startup prints the HTTP gateway URL for RobotArchitect.

## Start and observe

At the device's native prompt:

```python
import slide_nodes
slide_nodes.start()
print(slide_nodes.position())
```

Startup returns to the REPL and does not move the slide. Position samples use metres: `value=0.1` means 100 mm. Check that observations change when the target distance changes.

## Calibrate and move

```python
slide_nodes.calibrate(steps=1000)
slide_nodes.set_range(30, 300)
slide_nodes.demo(100)
slide_nodes.stop()
```

Only proceed to the target move after calibration succeeds. See [Linear Slide](linear-slide.html) for the calibration method and [Troubleshooting](troubleshooting.html) for noisy readings. To keep the slide service on one device and run commands from another, follow [Multiple Devices](deployment.html).
