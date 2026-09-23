"""Small shared helpers for command modules; no command dispatch or handlers."""
import os
try:
    import ujson as json
except ImportError:
    import json

vfses = {}


def require_node(context):
    if context.node is None:
        raise ValueError('this command requires an active node')
    return context.node


def human(size):
    if size > 1024 * 1024:
        return '{:.0f}MB'.format(size / (1024 * 1024))
    if size > 1024:
        return '{:.0f}KB'.format(size / 1024)
    return '{}B'.format(size)


def abs_path(path):
    if path.startswith('~'):
        path = '/' + path[1:].lstrip('/')
    if path.startswith('/'):
        return path
    return os.getcwd().rstrip('/') + '/' + path


def split_arguments(text):
    """Minimal portable shell quoting for paths; JSON handlers keep their raw tail."""
    result, token, quote, escaped, active = [], '', None, False, False
    for char in text:
        if escaped:
            token += char
            escaped = False
        elif char == '\\' and quote != "'":
            escaped = True
            active = True
        elif quote:
            if char == quote:
                quote = None
            else:
                token += char
        elif char in ('"', "'"):
            quote = char
            active = True
        elif char.isspace():
            if active:
                result.append(token)
                token, active = '', False
        else:
            token += char
            active = True
    if escaped or quote:
        raise ValueError('unfinished quote or escape')
    if active:
        result.append(token)
    return result


def entries(path):
    if hasattr(os, 'ilistdir'):
        return list(os.ilistdir(path))
    return [(name, os.stat(path.rstrip('/') + '/' + name)[0] & 0xf000, 0,
             os.stat(path.rstrip('/') + '/' + name)[6]) for name in os.listdir(path)]
