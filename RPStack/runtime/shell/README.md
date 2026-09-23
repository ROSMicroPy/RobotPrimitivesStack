# RPStack shell

Both `AsyncShell` and the standalone `sh.Shell` discover commands under `bin`.
The front ends handle terminal input, completion and dispatch; every command
implementation is in a command module. There is no integrated command table.

Declare `rpstack.shell.async_shell:AsyncShell` in the node manifest's `runtime`
list. Its console polls input and executes commands as tracked asyncio tasks.
Ctrl-C dispatches `stop`. `reset` reconstructs application services; `reboot`
and `restart` reset the physical board. HTTP and shell survive application
stop/reset. `quit` stops console input; the node stays available through its
other runtime interfaces until shutdown.

## Two command sets

`src/rpstack/shell/bin/core` ships with `package.json` / `package.local.json`:

- Node and services: `ps`, `status`, `execution`, `stop`, `reset`, `reboot`,
  `restart`, `kill`, `run`, `flow`, `signal`.
- Filesystem: `cat`, `cd`, `cp`, `df`, `ls`, `mkdir`, `mountsd`, `mv`, `pwd`,
  `ramdisk`, `rm`, `rmdir`, `touch`, `umount`.
- Console control and discovery: `help`, `quit`.

`src/rpstack/shell/bin/optional` ships as one separate package,
`optional/package.json` / `optional/package.local.json`:

`adc`, `blink`, `clear`, `edit`, `free`, `freq`, `httpd`, `ifconfig`, `mc`,
`memtest`, `modules`, `pystone`, `python`, `scani2c`, `set`, `telnet`, `telnetd`,
`temperature`, `time`, `uname`, `uptime`, `wait`, `wget`, `wifi`.

The core package excludes these commands and their bundled editor/server helper
modules. Install the optional set with one command once this revision is
published on the repository's `archdef` branch:

```python
import mip
mip.install("github:ROSMicroPy/RobotPrimitivesStack/RPStack/runtime/shell/optional", version="archdef")
```

The remote optional package depends on the core shell package. Local deployment
tools can use `optional/package.local.json`; the existing linear-slide local
package already includes the core shell's runtime dependencies. Hardware tools
still require their firmware modules. `edit`/`mc` require the corresponding
`mp_uemacs`/`uemacs` or `mp_mini_commander`/`mini_commander` installation, and
`wget` requires `requests`, as before.

Discovery runs against installed files, so newly installed commands appear on
the next invocation, help listing or completion request without restarting the
shell. It recognizes `.py`, `.mpy` and `.sh`, ignores underscore-prefixed
helpers, and does not import command modules to list them. Core names take
precedence over optional and registered external commands. Old flat `bin/*.py`
files left by an earlier installation are ignored.

## Command interface

```python
# bin/core/example.py or bin/optional/example.py
async def run(context, arguments):
    # arguments is the unmodified text after the command name.
    # context.node is the active NodeRuntime, or None in a standalone shell.
    # context.commands provides shared discovery and dispatch.
    print(arguments)
```

A quick command may use ordinary `def run`. Async commands are awaited by the
node console. The standalone shell runs them with asyncio, or schedules them in
the active node task registry when attached to a running node. No Python worker
threads or `&` commands are used by dispatch.

Use `support.split_arguments` for quoted filenames. Commands accepting JSON
split only their fixed positional prefix, preserving spaces and quotes in the
JSON tail. For example:

```text
run slide jog_steps {"steps": 100}
signal operator.continue {"message": "ready to proceed"}
cp "a directory" "backup directory"
```

`help` lists installed commands by group. `.sh` scripts execute lines in order,
awaiting async commands. `registercommand(path, class_name)` still adds external
class commands; both front ends discover the registry. Existing external
`run(argv)` conventions remain supported.

Commands that block or take over the terminal declare `FOREGROUND_ONLY = True`:
`edit`, `mc`, `memtest`, `pystone`, `python`, `telnet`, `wget`, `httpd`, `telnetd`.
They run in the standalone shell and are rejected in a node console so they
cannot block its lifecycle controls. Interactive `cat > PATH` has the same
restriction. `wait`, timed execution, GPIO demo delays and Wi-Fi connection
waiting yield to asyncio; large file copies, reads and removals also yield.
Custom async-console commands and external handlers must be cooperative.

Python execution is explicitly selected with the optional `python` command;
unknown command text is no longer implicitly executed as Python. `python`
without a filename enters the standalone Python session; `exit()` / `quit()`
returns to the shell. `python PATH [ARGS]` executes a script.

## Package maintenance

After adding commands or helper modules, regenerate both sets:

```sh
python3 RPStack/runtime/shell/tools/files2pkgjson.py
python3 -m unittest discover -s RPStack/runtime/shell/test -v
```

The generator keeps the packages disjoint. Host tests exercise discovery,
optional installation into a core-only tree, dispatch, JSON arguments,
filesystem commands, cancellation and nonblocking control. Hardware commands
are not executed by those tests.
