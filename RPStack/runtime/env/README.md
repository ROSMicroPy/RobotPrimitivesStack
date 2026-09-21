# Environment Store

The Environment Store provides shell-style configuration values for MicroPython. Values can exist only for the current session or persist across device restarts.

## Role in RPStack

Environment values are useful for operational settings shared by boot scripts, shell commands, bridges, and device assembly code. Service configuration that is part of a service contract belongs in its **component.yaml** manifest and instance configuration. The environment store is best suited to deployment-specific values such as endpoints, device names, feature flags, and credentials supplied by the device owner.

## Shell commands

Display all values:

~~~text
env
~~~

Set a session value:

~~~text
export DEVICE_NAME=lift-controller
~~~

Set a persistent value:

~~~text
export OTEL_ENDPOINT!=http://collector.local:4318
~~~

The **!=** operator marks the name as persistent. The **=** operator keeps the value in memory and removes persistence from that name if it was previously persistent.

Tokenized forms are also accepted:

~~~text
export DEVICE_NAME = lift controller
export OTEL_ENDPOINT != http://collector.local:4318
~~~

## Python API

~~~python
from rpstack.env import getEnv, setEnv, items, printEnv

setEnv("DEVICE_NAME", "lift-controller")
setEnv("OTEL_ENDPOINT", "http://collector.local:4318", True)

name = getEnv("DEVICE_NAME")
all_values = items()
printEnv()
~~~

The API normalizes values to strings.

| Function | Purpose |
|---|---|
| getEnv(name) | Return a value or None |
| setEnv(name, value, isPersistant=False) | Set a session or persistent value |
| items() | Return sorted name/value pairs |
| printEnv() | Print the sorted environment |
| loadPersistent() | Reload persistent values from storage |

The parameter name **isPersistant** uses the spelling in the public API.

## Persistence

Persistent values are stored as JSON at:

~~~text
/lib/etc/env/env.json
~~~

The package creates parent directories as needed. Importing the environment package loads the persistent file. The installed **S005_env.py** startup hook makes the values available early in the boot sequence.

## Installation

~~~python
import mip
mip.install(
    "https://gitlab.com/robot-primitives/Micropython_Modules/"
    "ide/mp_env/-/raw/main/package.json"
)
~~~

## Operational guidance

- Treat the persistence file as configuration, not as a secret vault.
- Use stable uppercase names for deployment-wide settings.
- Keep typed service values in instance configuration and convert environment strings explicitly.
- Use persistent values sparingly so device state remains understandable.

## Repository layout

- `src/` contains importable modules and device startup files.
- `test/` contains host tests or hardware-test guidance.
- `package.json` maps source files to their MIP installation paths.
- Optional `examples/` and `tools/` directories contain development-only resources.

## MIP installation

All file sources in `package.json` are relative to this component directory. The package installs its Python modules under `/lib/rpstack/env/`, allowing applications to import `rpstack.env`.

From this component directory:

~~~bash
mpremote mip install ./package.json
~~~

From the repository root:

~~~bash
mpremote mip install RPStack/runtime/env/package.json
~~~

From GitHub on the development branch:

~~~bash
mpremote mip install github:ROSMicroPy/RobotPrimitivesStack/RPStack/runtime/env@archdef
~~~

A raw manifest URL is also supported:

~~~bash
mpremote mip install https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/archdef/RPStack/runtime/env/package.json
~~~
