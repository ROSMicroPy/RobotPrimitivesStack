from rpstack.execution_engine.tasks import now_ms, elapsed_ms

async def run(context, arguments):
    started = now_ms()
    await context.commands.execute(context, arguments)
    milliseconds = elapsed_ms(started)
    print('{}m{}.{:03d}'.format(milliseconds // 60000, milliseconds // 1000 % 60, milliseconds % 1000))
