import os
from rpstack.support import asyncio
from rpstack.shell.support import entries, human, split_arguments

# List directory entries with type and size, yielding between output rows.
async def run(context, arguments):
    args = split_arguments(arguments)
    path = args[0] if args else os.getcwd()
    for item in sorted(entries(path)):
        name = item[0]
        stat = os.stat(path.rstrip('/') + '/' + name)
        kind = 'd' if stat[0] & 0x4000 else 'f'
        print('{} {}\t{}'.format(kind, human(stat[6]), name))
        await asyncio.sleep(0)
