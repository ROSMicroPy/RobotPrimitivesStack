'''
Created by Valentin Solina, Part of mipyshell project
Super simple, VT100 compatible, Command line interpreter helper class
'''

import sys
sread = sys.stdin.read
swrite = sys.stdout.write


class Cmd:
    # Prepare the editable command line, cursor, prompt, history, and loop state.
    def __init__(self):
        self._line = ""
        self._idx = 0
        self.prompt = "cmd> "
        self.history = []
        self._history_idx = 0
        self._running = True
    
    # Read terminal characters and escape sequences, dispatching editing keys until stopped.
    def cmdloop(self):
        self._running = True
        self.redraw_line()
        self._idx = 0
        skip_lf = False
        kmap_1ch = {'\x7f': self._backspace, '\t': self._tab, '\n': self._enter, '\r': self._enter}
        kmap_2ch = {'A': self._up, 'B': self._down, 'C': self._right, 'D': self._left, 'H': self._home, 'F': self._end}
        kmap_3ch = {'3': self._delete}
        while self._running:
            try:
                c = sread(1)
            except KeyboardInterrupt:
                swrite("\n")
                break
            if skip_lf and c == '\n':
                skip_lf = False
                continue
            skip_lf = False
            if c == '\x1b':
                c2 = sread(1)
                if c2 == '[':
                    c3 = sread(1)
                    if c3 in kmap_2ch.keys():
                        kmap_2ch[c3]()
                    elif c3 in kmap_3ch.keys():
                        _ = sread(1)
                        kmap_3ch[c3]()
            elif c in kmap_1ch.keys():
                kmap_1ch[c]()
                if c == '\r':
                    skip_lf = True
            else:
                if len(self._line) == self._idx:
                    self._line += c
                    self._idx += 1
                    swrite(c)
                else:
                    self._line = self._line[:self._idx] + c + self._line[self._idx:]
                    self._idx += 1
                    self.redraw_line()

    # Ask the command input loop to exit.
    def stop(self):
        self._running = False
    
    # Clear and repaint the prompt and buffer, restoring the cursor's logical position.
    def redraw_line(self):
        swrite("\033[256D")
        swrite("\033[2K")
        swrite(self.prompt)
        swrite(self._line)
        if len(self._line) - self._idx > 0:
            swrite("\033[{}D".format(len(self._line) - self._idx))

    # Provide the base command hook by printing the submitted command.
    def execute_command(self, command):
        print("Executing command: {}".format(command))

    # Leave input unchanged until a subclass supplies completion behavior.
    def complete(self, line):
        return line, False

    # Skip empty commands by default; interactive sessions may override this choice.
    def should_execute_empty_line(self):
        return False

    # Submit the current line, retain nonempty history, and reset the prompt buffer.
    def _enter(self):
        swrite("\n")
        if len(self._line) > 0 or self.should_execute_empty_line():
            if len(self._line) > 0:
                self.history.append(self._line)
            self.execute_command(self._line)

        self._line = ""
        if self._running:
            swrite(self.prompt)
            self._idx = 0
        self._history_idx = 0

    # Move the cursor left without crossing the start of input.
    def _left(self):
        if self._idx > 0:
            swrite("\033[{}D".format(1))
            self._idx -= 1

    # Move the cursor right without crossing the end of input.
    def _right(self):
        if self._idx < len(self._line):
            swrite("\033[{}C".format(1))
            self._idx += 1

    # Move the terminal cursor to the start of the editable line.
    def _home(self):
        swrite("\033[{}D".format(self._idx))
        self._idx = 0

    # Move the terminal cursor to the end of the editable line.
    def _end(self):
        swrite("\033[{}C".format(len(self._line)-self._idx))
        self._idx = len(self._line)

    # Remove the character before the cursor and redraw the edited line.
    def _backspace(self):
        if self._idx > 0:
            self._line = self._line[:self._idx-1] + self._line[self._idx:]
            self._idx -= 1
            self.redraw_line()

    # Remove the character under the cursor and redraw the line.
    def _delete(self):
        if self._idx < len(self._line):
            self._line = self._line[:self._idx] + self._line[self._idx+1:]
            self.redraw_line()

    # Apply the completion hook and redraw when it requests an update.
    def _tab(self):
        l, redraw = self.complete(self._line)
        if redraw:
            self._line = l
            self._idx = len(l)
            self.redraw_line()

    # Recall an older history entry when one is available.
    def _up(self):
        if len(self.history) > self._history_idx * -1:
            self._history_idx -= 1
            self._line = self.history[self._history_idx]
            self._idx = len(self._line)
            self.redraw_line()

    # Move toward a newer command in the retained history.
    def _down(self):
        if self._history_idx * -1 > 0:
            self._history_idx += 1
            self._line = self.history[self._history_idx]
            self._idx = len(self._line)
            self.redraw_line()


