import asyncio
import typing


def get_event_loop() -> typing.Optional[asyncio.AbstractEventLoop]:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return None

    return loop
