import asyncio


def get_event_loop() -> asyncio.AbstractEventLoop | None:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return None

    return loop
