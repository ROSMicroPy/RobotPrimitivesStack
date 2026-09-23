from rpstack.execution_engine import asyncio

async def run(context, arguments):
    await asyncio.sleep(float(arguments.strip()))
