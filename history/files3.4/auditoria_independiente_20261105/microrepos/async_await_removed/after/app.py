events = []
async def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])
async def work():
    monitor(1)
    protected(1)
def run():
    import asyncio
    asyncio.run(work())
