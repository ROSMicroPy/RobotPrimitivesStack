import sys
from rpstack.support import asyncio
from rpstack.shell.support import split_arguments

# Stream files to stdout, or capture interactive input into a file in the standalone shell.
async def run(context, arguments):
    args = split_arguments(arguments)
    if not args:
        raise ValueError('usage: cat PATH')
    if args[0] in ('>', '>>'):
        if getattr(context, 'is_async', False) or context.node is not None:
            raise ValueError('interactive cat requires the standalone shell')
        if len(args) != 2:
            raise ValueError('usage: cat > PATH or cat >> PATH')
        with open(args[1], 'a' if args[0] == '>>' else 'w') as handle:
            while True:
                char = sys.stdin.read(1)
                if not char or char == '\x1b':
                    break
                handle.write(char)
        return
    for path in args:
        with open(path) as handle:
            while True:
                chunk = handle.read(512)
                if not chunk:
                    break
                sys.stdout.write(chunk)
                await asyncio.sleep(0)
