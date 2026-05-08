import websockets
import websockets.exceptions

from inngest._internal import types

from . import models


def _is_connection_fatal_send_error(err: Exception) -> bool:
    return isinstance(
        err,
        (
            websockets.exceptions.ConnectionClosed,
            OSError,
            EOFError,
        ),
    )


async def safe_send(
    logger: types.Logger,
    state: models.State,
    message: bytes,
) -> types.MaybeError[None]:
    """
    Send a message to the WebSocket connection. If any error occurs, log and
    return the error. If the connection is closed, clear the WebSocket
    connection to trigger a reconnect.
    """

    ws: websockets.ClientConnection | None = None
    try:
        ws = state.ws.value
        if ws is None:
            return Exception("No WebSocket connection")
        await ws.send(message)
    except Exception as e:
        logger.error(f"Error sending message: {e!s}", extra={"error": str(e)})
        if ws is not None and _is_connection_fatal_send_error(e):
            state.close_ws_if_current(ws)
        return e

    return None
