# Optional shell commands

This directory contains the mip manifest for the complete non-core command set.
Implementations remain under `../src/rpstack/shell/bin/optional`; installing this
package places them alongside the core command directory on the device.

```python
import mip
mip.install("github:ROSMicroPy/RobotPrimitivesStack/RPStack/control/shell/optional", version="archdef")
```

Use the branch containing this revision. See the [shell documentation](../README.md)
for command membership, device/library prerequisites and foreground-only tools.
No additional registration or shell restart is required.
