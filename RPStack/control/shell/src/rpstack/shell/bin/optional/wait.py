from rpstack.support import asyncio

# Yield for the requested number of seconds without blocking the event loop.
async def run(context, arguments):
    await asyncio.sleep(float(arguments.strip()))
