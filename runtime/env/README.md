# mp_env

`mp_env` adds a small, shell-oriented environment store to MicroPython systems. It gives command-driven workflows a place to keep configuration without hardcoding everything into scripts or sprinkling settings files across the device.

**Project URL**: https://gitlab.com/robot-primitives/Micropython_Modules/ide/mp_env

> **Standout:** uses a tiny but memorable persistence model: `NAME=value` for the session, `NAME!=value` for values that survive reboot.

## Core capabilities

- `env` prints the current environment
- `export NAME=value` stores a session variable
- `export NAME!=value` stores a persistent variable
- persisted values are reloaded at boot through the startup hook

## Install with `mip`

```python
import mip
mip.install("https://gitlab.com/robot-primitives/Micropython_Modules/ide/mp_env/-/raw/main/package.json")
```

## Why it matters

This project is small by design, but it solves a real coordination problem across the stack. Shell commands, sync tooling, and boot-time integrations all benefit when runtime configuration has one predictable home.
