'''
Created by Valentin Solina, Part of mipyshell project
Super simple, MicroPython based, VT100 compatible POSIX shell imitation
'''

import uos
import os
import network
import micropython
import sys
import machine
import gc
import time
from mpshell import registry
from mpshell.cmd import Cmd

try:
    import builtins as _builtins_module
except ImportError:
    _builtins_module = None


## Internal variables
next_thread_index = 1
_active_threads = {}
_active_threads_ksignal = {}

_vfses = {}
_shell_instance = None
_external_command_defs = {}

_threads_enabled = False
try:
    import _thread
    _threads_enabled = True
except:
    pass


## Utility functions
def root_info():
    info = uos.statvfs("/")
    block_size = info[0]
    fragment_size = info[1]
    fragment_count = info[2]
    free_block_count = info[3]
    
    print ("Root FS size {} Free {}".format(fragment_size * fragment_count, block_size * free_block_count))

def human(bytes):
    if bytes > 1024:
        if bytes > 1024 * 1024:
            return "{:.0f}MB".format(bytes / (1024 * 1024))
        else:
            return "{:.0f}KB".format(bytes / 1024)
    return "{}B".format(bytes)

def home_dir():
    return "/"

def rediscover_commands():
    global _external_command_defs
    discovered = {}
    for entry in registry.read_ext_registry():
        try:
            loaded = registry.load_external_command(entry)
            discovered[loaded["name"]] = loaded
        except Exception as e:
            print("Failed to load external command {} {}".format(entry.get("path"), entry.get("class")))
            sys.print_exception(e)
    _external_command_defs = discovered
    return discovered

def abs_path(path):
    comp = path.split("/")
#    if comp[-1] != "":
#        path += "/"
    if comp[0] == "":
        return path
    if comp[0] == "~":
        return home_dir() + path[1:]
    cwd = os.getcwd()
    if cwd[0] != "/":
        cwd = "/" + cwd
    if cwd[-1] != "/" and path[0] != "/":
        cwd += "/"
    return cwd + path

def _resolve_code_dir():
    # Some MicroPython builds do not define __file__ for imported modules.
    # Probe the common installed locations and return the first valid package dir.
    candidates = []
    try:
        current_file = __file__
        candidates.append(current_file.rsplit('/', 1)[0] if '/' in current_file else '.')
    except NameError:
        pass

    candidates.extend((
        "/lib/mpshell",
        "mpshell",
        "./mpshell",
    ))

    seen = {}
    for code_dir in candidates:
        if not code_dir or code_dir in seen:
            continue
        seen[code_dir] = True
        try:
            os.ilistdir(code_dir + "/bin")
            return code_dir
        except OSError:
            pass
    return None

def get_bins():
    pybins = {}
    shbins = {}
    code_dir = _resolve_code_dir()
    if code_dir is None:
        return pybins, shbins

    for f, type, unknown_param, inode in os.ilistdir(f"{code_dir}/bin"):
        if f.endswith(".py"):
            fname = f[:-3]
            pybins[fname] = f"{code_dir}/bin/{f}"
        if f.endswith(".sh"):
            fname = f[:-3]
            shbins[fname] = f"{code_dir}/{f}"
    return pybins, shbins


def has_command(cmd_name):
    py_bins, sh_bins = get_bins()
    return (
        cmd_name in cmds_integrated
        or cmd_name in py_bins
        or cmd_name in sh_bins
        or cmd_name in _external_command_defs
    )


## Commands
def mkdir_imp(args):
    if len(args) < 2:
        print("Usage: mkdir <path>")
        return
    path = args[1]
    print ("creating dir {}".format(abs_path(path)))
    os.mkdir(path)

def rmdir_imp(args):
    path = args[1]
    os.rmdir(path)

def touch_imp(args):
    path = args[1]
    with open(path, 'a'):
        try:
            os.utime(path, None)
        except Exception as e:
            pass # micropython has no utime

def cd_imp(args):
    path = args[1]
    os.chdir(path)

def pwd_imp(args):
    print(abs_path(os.getcwd()))

def rm_imp(args):
    if len(args) < 2:
        print("Usage: rm <path>")
        return
    path = args[1]
    _remove_path(path)

def _is_dir(path):
    return (os.stat(path)[0] & 0x4000) != 0

def _join_path(parent, child):
    if parent == "/":
        return "/" + child
    if parent.endswith("/"):
        return parent + child
    return parent + "/" + child

def _remove_path(path):
    if _is_dir(path):
        for entry in os.ilistdir(path):
            _remove_path(_join_path(path, entry[0]))
        os.rmdir(path)
    else:
        os.remove(path)

def free_imp(args):
    micropython.mem_info()

def reset_imp(args):
    machine.reset()

def modules_imp(args):
    print (sys.modules)

def time_imp(args):
    s = time.ticks_ms()
#    print("Executing {}".format(
    execute_command(" ".join(args[1:]))
    ms = time.ticks_ms() - s
    minutes = ms // 60000
    seconds = (ms - minutes*60000) // 1000
    print ("{}m{}.{:0>3}".format(minutes, seconds, ms % 1000))


## Special commands
def python_imp(args):
    if len(args) == 1:
        global alive
        alive = False
        return
    
    script_name = args[1]
    if len(script_name.split(".")) > 1:
        script_name = script_name[:-3]
    
    try:
        pys = __import__(script_name)
        if '__main__' in dir(pys):
            pys.__main__(args)
    except Exception as e:
        print ("Error executing script {}".format(script_name))
        sys.print_exception(e)
    
    # TODO: ovo moze exeptat "KeyError: /bin/pystone" ako je vec deletan; treba stavit if script_name in modules
    del sys.modules[script_name]

def quit_imp(args):
    global alive
    global _shell_instance
    alive = False
    if _shell_instance is not None:
        _shell_instance.stop()

alive = True

## Integrated command mapping
cmds_integrated = {
             "mkdir": mkdir_imp,
             "rmdir": rmdir_imp,
             "touch": touch_imp,
             "cd": cd_imp,
             "pwd": pwd_imp,
             "rm": rm_imp,
             "free": free_imp,
             "restart": reset_imp,
             "reboot": reset_imp,
             "reset": reset_imp,
             "python": python_imp,
             "time": time_imp,
             "quit": quit_imp}

def all_commands(start):
    py, sh = get_bins()
    cmds = list(cmds_integrated.keys()) + list(py.keys()) + list(sh.keys()) + list(_external_command_defs.keys())
    if len(start) > 0:
        cmds = list(filter(lambda k: k.startswith(start), cmds))
    return sorted(cmds)

def _run_external_command(command_def, args):
    instance = command_def["instance"]
    if hasattr(instance, "run"):
        return instance.run(args)
    if hasattr(instance, "__main__"):
        return instance.__main__(args)
    raise AttributeError("External command has no run() or __main__()")

if _threads_enabled:
    def _run_thread(args, command, _func):
        global _active_threads
        global _active_threads_ksignal
        
        tid = _thread.get_ident()
        _active_threads_ksignal[tid] = -1
        def _thread_watchdog(timer):
            if _active_threads_ksignal[tid] != -1:
                timer.deinit()
                def _quit(msg):
                    print ("Quitting from {}".format(_thread.get_ident()))
                    _thread.exit()
    #                raise Exception(msg)
    #             micropython.schedule(_quit, ("[{}] Kill thread signal {}".format(tid, _active_threads_ksignal[tid])))
                print ("Quitting from {}".format(_thread.get_ident()))
                _thread.exit()
                _thread.exit()
        
        _active_threads[tid] = (command, time.ticks_us())
        print ("[1] {}".format(tid))
        try:
            timer = machine.Timer(-1)
            #timer.init(period=100, mode=machine.Timer.PERIODIC, callback=_thread_watchdog)
            
            _func(args)
            timer.deinit()
            del _active_threads[tid]
            print ("Exited [{}] {}".format(tid, command))
            gc.collect()
        except Exception as e:
            timer.deinit()
            del _active_threads[tid]
            print ("Exited [{}] {}".format(tid, command))
            gc.collect()
            raise e

def execute_command(command):
    if command.endswith("&"):
        if not _threads_enabled:
            print ("Backgrounding (threading) is not available")
            return True
        #global _active_threads
        #global _next_thread_index
        
        args = command[:-1].split(" ")
        #new_thread = 
        _thread.start_new_thread(_run_thread, (args, command, _exec_cmd))#TODO: ovo moze exceptat MemoryError: memory allocation failed
        #td = (new_thread, command)
        #_active_threads[_next_thread_index] = td
        return True
    else:
#        args = command.strip().split(" ")
        args = list(filter(lambda s: len(s) > 0, command.strip().split(" ")))
        return _exec_cmd(args)

def _exec_cmd(args):
    if not args:
        return True
    cmd_name = args[0]
    py_bins, sh_bins = get_bins()
    if cmd_name in cmds_integrated:
        try:
            gc.collect()
            result = cmds_integrated[cmd_name](args)
            if result != None:
                print (result)
            return True
        except Exception as e:
            print ("Error executing command")
            sys.print_exception(e)
            return True
    elif cmd_name in py_bins:
        _args = ['python', py_bins[cmd_name]]
        _args.extend(args[1:])
        python_imp(_args)
        return True
    elif cmd_name in sh_bins:
        execute_script(sh_bins[cmd_name])
        return True
    elif cmd_name in _external_command_defs:
        try:
            gc.collect()
            result = _run_external_command(_external_command_defs[cmd_name], args)
            if result != None:
                print(result)
            return True
        except Exception as e:
            print("Error executing external command")
            sys.print_exception(e)
            return True
    else:
        return False

def execute_script(name):
    with open(name) as f:
        for line in f.readlines():
            line = line.rstrip()
            if len(line) > 0:
                execute_command(line)

'''
def shell(args):
    execute_command("init")
    while (alive):
    #    ip = w.ifconfig()[0]
        ip = "machine"
        prompt = "{}:{} upy$ ".format(ip, os.getcwd())
        command = input(prompt)
        try:
            execute_command(command)
        except KeyboardInterrupt:
            print ("Keyboard interrupt")
            pass
    
    del sys.modules["mpshell.sh"]
'''

#_thread.start_new_thread(_run_thread, ([], "sh", shell))

##_run_thread([], "sh", shell)
#TODO: support for subpaths
def complete_dir(start):
#    cmps = start.split("/")
    if start.startswith("/"):
        start = start[1:]
    cwd = os.getcwd()
    files = os.listdir(cwd)
    if len(start) > 0:
        files = list(filter(lambda k: k.startswith(start), files))
    return files


class Shell(Cmd):
    def __init__(self, run_init=True):
        super().__init__()
        global _shell_instance
        _shell_instance = self
        self._mode = "shell"
        self._python_fallback_active = False
        self._python_buffer = []
        self._python_namespace = self._python_globals()
        registry.set_refresh_handler(rediscover_commands)
        rediscover_commands()
        self.update_prompt()
        if run_init and has_command("init"):
            execute_command("init")

    def update_prompt(self):
        if self._mode == "python" or self._python_fallback_active:
            cwd = abs_path(os.getcwd())
            if self._python_buffer:
                self.prompt = "py:{} cont$ ".format(cwd)
            else:
                self.prompt = "py:{} exec$ ".format(cwd)
            return

        ip = "machine"
        self.prompt = "{}:{} upy$ ".format(ip, os.getcwd())

    def _python_globals(self):
        main_module = sys.modules.get("__main__")
        namespace = getattr(main_module, "__dict__", None)
        if namespace is None:
            namespace = globals()
        if "__builtins__" not in namespace:
            builtins_obj = globals().get("__builtins__")
            if builtins_obj is None:
                builtins_obj = _builtins_module
            if builtins_obj is not None:
                namespace["__builtins__"] = builtins_obj
        return namespace

    def enter_python_repl(self):
        self._mode = "python"
        self._python_buffer = []
        self.update_prompt()
        print("Python REPL mode. Use exit() or quit() to return to the shell.")
        print("Using mp_shell Python prompts to avoid colliding with Thonny's native REPL handling.")

    def exit_python_repl(self):
        self._mode = "shell"
        self._python_fallback_active = False
        self._python_buffer = []
        self.update_prompt()

    def _python_source_incomplete(self, source, err):
        message = str(err)
        incomplete_markers = (
            "unexpected EOF",
            "EOF while scanning",
            "expected an indented block",
            "after function definition on line",
            "after for loop on line",
            "after while loop on line",
            "after if statement on line",
            "after elif statement on line",
            "after else statement on line",
            "after try statement on line",
            "after except clause on line",
            "after finally clause on line",
            "after with statement on line",
            "after class definition on line",
        )
        for marker in incomplete_markers:
            if marker in message:
                return True
        if source.endswith(":") or source.endswith("\\"):
            return True
        return False

    def _python_block_pending(self):
        if not self._python_buffer:
            return False

        last = self._python_buffer[-1]
        if not last.strip():
            return False

        stripped = last.lstrip()
        if last.endswith(":") or last.endswith("\\"):
            return True
        if stripped.startswith(("elif ", "else:", "except", "finally:")):
            return True
        return False

    def _run_python_expr(self, source):
        try:
            result = eval(source, self._python_namespace, self._python_namespace)
        except SyntaxError:
            return False

        if result is not None:
            print(repr(result))
        return True

    def _run_python_stmt(self, source):
        exec(source, self._python_namespace, self._python_namespace)

    def _execute_python_line(self, command):
        stripped = command.strip()
        if not self._python_buffer and stripped in ("exit()", "quit()"):
            if self._mode == "python":
                self.exit_python_repl()
            else:
                self._python_fallback_active = False
                self._python_buffer = []
                self.update_prompt()
            return

        if not self._python_buffer and not stripped:
            self.update_prompt()
            return

        self._python_buffer.append(command)

        if self._python_block_pending():
            self.update_prompt()
            return

        if not stripped and len(self._python_buffer) == 1:
            self._python_buffer = []
            self.update_prompt()
            return

        source = "\n".join(self._python_buffer).strip()
        try:
            if len(self._python_buffer) == 1 and stripped:
                if self._run_python_expr(source):
                    self._python_buffer = []
                    self.update_prompt()
                    return
            self._run_python_stmt(source)
        except Exception as err:
            if isinstance(err, SyntaxError) and self._python_source_incomplete(source, err):
                self.update_prompt()
                return
            sys.print_exception(err)

        self._python_buffer = []
        if self._mode != "python":
            self._python_fallback_active = False
        self.update_prompt()

    def complete(self, line):
        if self._mode == "python":
            return line, False

        seg = line.split(" ")
        if len(seg) == 1:
            cmds = all_commands(seg[0])
            if len(cmds) == 1:
                return cmds[0]+" ", True
            if len(cmds) == 0:
                return line, False
            print ('')
            for cmd in cmds:
                sys.stdout.write(cmd+'\t')
            print ('')
        if len(seg) > 1:
            files = complete_dir(seg[-1])
            if len(files) == 1:
                preline = "/".join(seg[:-1])
                return preline + " " + files[0]+" ", True
            if len(files) == 0:
                return line, False
            print ('')
            for file in files:
                sys.stdout.write(file+'\t')
            print ('')
        return line, True

    def should_execute_empty_line(self):
        return (self._mode == "python" or self._python_fallback_active) and len(self._python_buffer) > 0

    def execute_command(self, cmd):
        try:
            if self._mode == "python":
                self._execute_python_line(cmd)
            else:
                handled = execute_command(cmd)
                if not handled:
                    self._python_fallback_active = True
                    self._execute_python_line(cmd)
        except KeyboardInterrupt:
            print ("Keyboard interrupt")
            if self._mode == "python" or self._python_fallback_active:
                self._python_buffer = []
                if self._mode != "python":
                    self._python_fallback_active = False
            pass
        self.update_prompt()

    @staticmethod
    def cmd(command, run_init=True):
        shell = Shell(run_init=run_init)
        shell.execute_command(command)
        return shell


def start(run_init=True):
    global alive
    alive = True
    shell = Shell(run_init=run_init)
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print("Shell interrupted")
    return shell


def cmd(command, run_init=True):
    return Shell.cmd(command, run_init=run_init)

#shell()

def clear():
    if "mpshell.sh" in sys.modules:
        del sys.modules["mpshell.sh"]
    if "sh" in sys.modules:
        del sys.modules["sh"]
