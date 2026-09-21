# Boot Manager

The Boot Manager provides deterministic startup for MicroPython devices. It loads small startup modules from an **init.d** directory and runs them in filename order.

## Role in RPStack

The Boot Manager starts runtime facilities such as environment loading, service assembly, observability, and shell integration. It is intentionally limited to boot sequencing. Capability binding and service lifecycle management belong to **PrimitiveRuntime**.

A typical startup flow is:

~~~text
main.py
  → bootmgr.run()
    → S005_env.py
    → device service registration
    → PrimitiveRuntime.start()
    → S999_mp_shell.py
~~~

## Startup script names

A startup module must:

- begin with **S**;
- contain at least two numeric ordering digits;
- include an underscore after the number;
- end in **.py**.

Examples:

~~~text
S005_env.py
S100_device_services.py
S999_mp_shell.py
~~~

Files are sorted lexically, so zero-padded numbers make execution order obvious.

Each module may define a **run()** function:

~~~python
def run():
    print("Starting device services")
~~~

The Boot Manager loads the module and calls **run()** when it is present. Top-level module code also runs during loading.

## init.d discovery

The loader searches practical locations associated with the installed package and device filesystem, including:

~~~text
/init.d
/lib/init.d
init.d
~~~

The first accessible directory is used.

## Bootstrapping main.py

~~~python
import bootmgr
bootmgr.bootstrap()
~~~

**bootstrap()** ensures that **main.py** imports the Boot Manager and calls **bootmgr.run()**. It also installs the default operational applications configured by the package.

Use **bootmgr.run()** directly when the device image or application already controls package installation.

## Installation

Install through the package manifest:

~~~python
import mip
mip.install(
    "https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/"
    "archdef/RPStack/runtime/bootmgr/package.json"
)
~~~

## Relationship to PrimitiveRuntime

The Boot Manager answers, “Which startup modules run, and in what order?”

PrimitiveRuntime answers:

- which services are available;
- how capability dependencies are bound;
- how services are configured and initialized;
- which order services start and stop;
- which operations and tests are exposed.

A boot script commonly constructs a **ServiceSupervisor**, registers the device services, and calls **start()**.

## Operational guidance

- Keep boot scripts small and delegate work to packages.
- Give infrastructure an early number and interactive tools a late number.
- Avoid long blocking work at module import time.
- Catch and report failures where a device should continue in a degraded mode.
- Let PrimitiveRuntime control service shutdown and dependency order.

## Repository layout

- `src/` contains importable modules and device startup files.
- `test/` contains host tests or hardware-test guidance.
- `package.json` maps source files to their MIP installation paths.
- Optional `examples/` and `tools/` directories contain development-only resources.

## MIP installation

All file sources in `package.json` are relative to this component directory. The package installs its Python modules under `/lib/rpstack/bootmgr/`, allowing applications to import `rpstack.bootmgr`.

From this component directory:

~~~bash
mpremote mip install ./package.json
~~~

From the repository root:

~~~bash
mpremote mip install RPStack/runtime/bootmgr/package.json
~~~

From GitHub on the development branch:

~~~bash
mpremote mip install github:ROSMicroPy/RobotPrimitivesStack/RPStack/runtime/bootmgr@archdef
~~~

A raw manifest URL is also supported:

~~~bash
mpremote mip install https://raw.githubusercontent.com/ROSMicroPy/RobotPrimitivesStack/archdef/RPStack/runtime/bootmgr/package.json
~~~
