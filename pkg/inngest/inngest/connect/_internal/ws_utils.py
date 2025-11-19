import websockets

from inngest._internal import types

from . import value_watcher


async def safe_send(
    logger: types.Logger,
    value_watcher: value_watcher._ValueWatcher[
        websockets.ClientConnection | None
    ],
    ws: websockets.ClientConnection,
    message: bytes,
) -> types.MaybeError[None]:
    """
    Send a message to the WebSocket connection. If any error occurs, log and
    return the error. If the connection is closed, clear the WebSocket
    connection to trigger a reconnect.
    """

    try:
        await ws.send(message)
    except websockets.exceptions.ConnectionClosed as e:
        logger.error(f"Error sending message: {e!s}", extra={"error": str(e)})
        value_watcher.value = None
        return e
    except Exception as e:
        logger.error(f"Error sending message: {e!s}", extra={"error": str(e)})
        return e

    return None
