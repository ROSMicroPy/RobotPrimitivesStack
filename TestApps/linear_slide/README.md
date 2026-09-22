# Linear slide hardware test

This application exercises the step/direction motor and VL53L4CD distance
sensor as one linear-slide service.

## Local installation from a private clone

Run the installer from this directory. The local manifest paths are intentionally
relative to this working directory because `mpremote mip` does not rebase
dependency paths against the parent manifest.

```sh
cd TestApps/linear_slide
mpremote mip install package.json
```

The installation writes `main.py` to `/lib/main.py` and installs the local
RPStack component packages beneath `/lib/rpstack/`.

## Remote installation

`package.github.json` retains GitHub component dependencies for use after the
repository is public or the packages are published to an accessible host.
Stock `mpremote` cannot authenticate its `github:` downloads against a
private repository.

## REST service

On boot the application connects to Wi-Fi, constructs the linear slide, loads
`/lib/linear_slide_manifest.json`, registers the manifest and operation
routes, and starts `MicroPyServer` on port 80. It does not move the slide
automatically.

The Web Tester discovers the device at:

```text
GET http://<device-ip>/manifest
```

The manifest declares position, status, stop, metre-based movement, and
millimetre-based compatibility endpoints. I²C uses SCL GPIO 4 and SDA GPIO 5;
the VL53L4CD address is `0x29`.
