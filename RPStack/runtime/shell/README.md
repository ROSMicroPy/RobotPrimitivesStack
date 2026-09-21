# MicroPython Shell

The shell provides an interactive and programmatic command environment for RPStack devices. It supplies common filesystem, networking, diagnostic, and device-management commands.

The package installs as **mpshell**.

## Role in RPStack

The shell is the operator-facing runtime component. It can inspect a device, launch diagnostics, edit files, configure networking, and invoke administrative commands. Service-specific control should use manifest-declared operations so the same contracts can be shared by the shell, WebTester, and network bridges.

## Starting the shell

Execute one command:

~~~python
from mpshell import sh

sh.cmd("help")
sh.cmd("ls /lib")
~~~

Start the interactive loop:

~~~python
from mpshell import sh

sh.start()
~~~

The installed **S999_mp_shell.py** boot module imports the shell late in the boot sequence. Interactive startup remains an application choice.

## Command model

The shell includes commands for:

- filesystem work: ls, cat, cp, mv, mkdir, rm, df;
- device inspection: uname, uptime, temperature, freq, memtest;
- task control: ps, kill, wait;
- hardware diagnostics: adc, blink, scani2c;
- networking: wifi, ifconfig, wget, telnet, telnetd, httpd;
- storage: mountsd, umount, ramdisk;
- editing and utilities: edit, mc, pystone, clear, help.

Input that is not resolved as a shell command can be evaluated through the Python fallback.

Append **&** where supported to run a command as a background task.

## External commands

Command extensions are recorded in:

~~~text
/lib/etc/mpshell/extcmds.json
~~~

An external command implements the shell contract:

~~~python
from mpshell import ExternalCommand

class ServiceStatusCommand(ExternalCommand):
    name = "service-status"

    def run(self, args):
        print(runtime.status(args[1]))
~~~

Register the module path and class:

~~~python
from mpshell import registercommand

registercommand(
    "/lib/device_commands.py",
    "ServiceStatusCommand",
)
~~~

The registry avoids duplicate path/class entries and refreshes the active command set when a refresh handler is installed.

## Manifest-driven service commands

A generic RPStack shell command can inspect a service manifest and expose:

- operation names;
- argument descriptions;
- units and ranges;
- return types;
- service status;
- automatic tests;
- manual or hardware tests with an approval prompt.

Generic tooling should call **ServiceSupervisor.invoke()** instead of accessing arbitrary object methods. This preserves the manifest allowlist and argument validation.

## Installation

~~~python
import mip
mip.install(
    "https://gitlab.com/robot-primitives/Micropython_Modules/"
    "ide/mp_shell/-/raw/main/package.json"
)
~~~

## Operational security

Commands such as telnet, HTTP serving, file editing, and arbitrary Python evaluation provide significant device access.

- Bind network services only to trusted interfaces.
- Require authentication in a deployment bridge.
- Do not expose the interactive shell directly to an untrusted network.
- Mark motion tests as hardware tests and require operator approval.
