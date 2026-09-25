"""Download a URL through the standalone shell's command interface."""

import sys

import requests

from rpstack.shell.support import split_arguments

FOREGROUND_ONLY = True


# Stream a URL to a file or stdout and release both streams when the command finishes.
def run(context, arguments):
    args = split_arguments(arguments)
    if not 1 <= len(args) <= 2:
        raise ValueError('usage: wget URL [PATH|-]')
    url = args[0]
    filename = args[1] if len(args) == 2 else url.split('?', 1)[0].rsplit('/', 1)[-1] or 'index'
    response = requests.get(url)
    output = None
    try:
        if filename != '-':
            output = open(filename, 'wb')
        total = 0
        while True:
            chunk = response.raw.read(4096)
            if not chunk:
                break
            if output is None:
                sys.stdout.write(chunk.decode('utf-8'))
            else:
                output.write(chunk)
            total += len(chunk)
        if output is not None:
            print('{} => {} ({} bytes)'.format(url, filename, total))
    finally:
        try:
            if output is not None:
                output.close()
        finally:
            response.close()
