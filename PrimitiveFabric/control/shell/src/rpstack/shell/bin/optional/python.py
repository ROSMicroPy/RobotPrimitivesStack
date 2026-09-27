import sys
from rpstack.shell.support import split_arguments

FOREGROUND_ONLY = True
try:
    import builtins as _builtins_module
except ImportError:
    _builtins_module = None

class PythonSession:
    # Prepare an embedded Python session with a shared namespace and multiline input buffer.
    def __init__(self, context):
        self.context = context
        self._mode = 'python'
        self._python_buffer = []
        self._python_fallback_active = False
        self._python_namespace = self._python_globals()
        self.update_prompt()

    # Show a continuation prompt while a Python block is incomplete.
    def update_prompt(self):
        self.context.prompt = '... ' if self._python_buffer else 'py> '

    # Feed a submitted terminal line into the Python input evaluator.
    def execute_command(self, command):
        self._execute_python_line(command)

    # Allow blank lines to finish buffered Python blocks.
    def should_execute_empty_line(self):
        return bool(self._python_buffer)

    # Reuse the main interpreter namespace and ensure builtins are available.
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

    # Reset multiline state and announce the shell-managed Python prompt.
    def enter_python_repl(self):
        self._mode = "python"
        self._python_buffer = []
        self.update_prompt()
        print("Python REPL mode. Use exit() or quit() to return to the shell.")
        print("Using mp_shell Python prompts to avoid colliding with Thonny's native REPL handling.")

    # Detach the Python session and clear buffered input before returning to the shell.
    def exit_python_repl(self):
        self.context.session = None
        self._mode = "shell"
        self._python_fallback_active = False
        self._python_buffer = []
        self.update_prompt()

    # Recognize syntax-error messages and source endings that indicate more input is needed.
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

    # Detect block headers or continuations that should wait for another input line.
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

    # Evaluate an expression and display its value, leaving statements for the execution path.
    def _run_python_expr(self, source):
        try:
            result = eval(source, self._python_namespace, self._python_namespace)
        except SyntaxError:
            return False

        if result is not None:
            print(repr(result))
        return True

    # Execute buffered Python statements in the session's shared namespace.
    def _run_python_stmt(self, source):
        exec(source, self._python_namespace, self._python_namespace)

    # Handle session exit, accumulate multiline input, and evaluate complete expressions or
    # statements.
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
            print(str(err))

        self._python_buffer = []
        if self._mode != "python":
            self._python_fallback_active = False
        self.update_prompt()


# Enter embedded Python mode or execute a file with temporary script arguments.
def run(context, arguments):
    args = split_arguments(arguments)
    if not args:
        context.session = PythonSession(context)
        print('Python mode. Use exit() or quit() to return to the shell.')
        return
    path = args[0]
    with open(path) as handle:
        code = handle.read()
    previous = sys.argv
    try:
        sys.argv = args
        exec(code, {'__name__': '__main__', '__file__': path})
    finally:
        sys.argv = previous
