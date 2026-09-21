# mp_shell

`mp_shell` is an extensible shell for MicroPython boards that want to behave more like working machines and less like passive deployment targets. It gives the device a command surface, a `/bin` model, and a usable automation loop.

**Project URL**: https://gitlab.com/robot-primitives/Micropython_Modules/ide/mp_shell

> **Standout:** provides a usable on-device shell with a command surface that can still be driven programmatically through `sh.cmd(...)`.

## Core capabilities

- built-in filesystem and runtime commands
- extensible `/bin` command discovery
- background task support with `&`
- command completion and line editing
- automatic Python fallback for input that is not a shell command
- helpers such as Wi-Fi setup, telnet, HTTP serving, editor launch, benchmarks, and device utilities

## Install with `mip`

```python
import mip
mip.install("https://gitlab.com/robot-primitives/Micropython_Modules/ide/mp_shell/-/raw/main/package.json")
```

## Use it

One-shot command execution:

```python
from mpshell import sh
sh.cmd("help")
```

Start the interactive shell:

```python
from mpshell import sh
sh.start()
```

## Why it matters

Most MicroPython command loops are either too bare to be productive or too hard to automate. `mp_shell` makes a better tradeoff:

- it is useful on-device
- it is scriptable
- it falls back to Python execution when input is not a shell command

That makes it the operational center of this stack.
