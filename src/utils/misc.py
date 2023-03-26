import asyncio

async def delay_coro(coro, seconds: float):
    """
    execute coroutine after given delay
    """
    try:
        await asyncio.sleep(seconds)
        await coro
    except asyncio.CancelledError:
        print("cancelled error")
