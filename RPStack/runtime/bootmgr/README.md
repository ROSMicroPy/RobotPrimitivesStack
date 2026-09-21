# mp_bootmgr

Boot orchestration for MicroPython does not need to be large to be useful. `mp_bootmgr` provides an `init.d`-style startup layer that lets related services register themselves as ordered boot scripts instead of fighting for space in `boot.py`.

**Project URL**: https://gitlab.com/robot-primitives/Micropython_Modules/mp_bootmgr

> **Standout:** turns MicroPython startup into an ordered service pipeline, which is the foundation that lets the rest of the toolchain feel like a system rather than a set of loose files.

## What it does

- locates an `init.d` directory from several practical candidate paths
- selects startup files named like `S003_name.py`
- sorts them by numeric prefix
- imports and runs their `run()` functions in order

That is enough structure to make shell services, environment loading, and other boot-time integrations predictable.

## Install with `mip`

```python
import mip
mip.install("https://gitlab.com/robot-primitives/Micropython_Modules/mp_bootmgr/-/raw/main/package.json")
```

## Why it matters

MicroPython projects often start with one file and end with a fragile boot script full of side effects. `mp_bootmgr` gives that growth path a cleaner destination.

## Typical use

- install `mp_bootmgr`
- drop startup modules into `init.d/`
- name them with ordered prefixes
- let `bootmgr.run()` activate the stack in a deterministic sequence
