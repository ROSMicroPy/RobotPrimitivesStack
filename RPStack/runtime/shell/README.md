# Async node shell

Declare `rpstack.shell.async_shell:AsyncShell` in the node manifest's `runtime`
list. The console polls input without blocking the shared asyncio loop. Each
command runs as a tracked task; `ps`, stop, and reset remain available while
operations or workflows are running.

Commands: `ps`, `status`, `stop`, `reset`, `kill ID`,
`run SERVICE OPERATION [JSON]`, `flow NAME`, and `signal NAME [JSON]`.
Ctrl-C requests an application stop. Reset reconstructs application services and
does not reboot the board. The HTTP listener and console survive both controls.

`ps` uses the node task registry. The old shell `_active_threads`, thread
watchdog, background `&`, and execution-engine threading APIs are removed.
The older standalone shell utility modules are not used by the node console.
External command registration exports remain available for the environment
package's init hook; the node console's command set is explicit.
