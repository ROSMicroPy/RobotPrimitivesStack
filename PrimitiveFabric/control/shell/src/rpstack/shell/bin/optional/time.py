from rpstack.support import now_ms, elapsed_ms

# Measure a nested shell command and print its elapsed_ms minutes, seconds, and milliseconds.
async def run(context, arguments):
    started = now_ms()
    await context.commands.execute(context, arguments)
    milliseconds = elapsed_ms(started)
    print('{}m{}.{:03d}'.format(milliseconds // 60000, milliseconds // 1000 % 60, milliseconds % 1000))
