import datetime
import unittest.mock

import test_core

from .heartbeat_handler import _HeartbeatHandler
from .models import ConnectionState, _State, _ValueWatcher


class TestHeartbeatHandle(unittest.IsolatedAsyncioTestCase):
    async def test_send_error(self) -> None:
        # Count the number of times we send a heartbeat
        count_sends = 0

        # Create a mock WebSocket connection that always fails to send
        class _MockWS(unittest.mock.AsyncMock):
            async def send(self, *args: object, **kwargs: object) -> None:
                nonlocal count_sends
                count_sends += 1
                raise Exception("oh no")

        mock_ws = _MockWS()

        handler = _HeartbeatHandler(
            logger=unittest.mock.Mock(),
            state=_State(
                conn_id=None,
                conn_init=_ValueWatcher(None),
                conn_state=_ValueWatcher(ConnectionState.ACTIVE),
                exclude_gateways=[],
                extend_lease_interval=_ValueWatcher(None),
                fatal_error=_ValueWatcher(None),
                ws=_ValueWatcher(mock_ws),
            ),
        )
        handler.start()

        # Ensure that we send 2 heartbeats. This ensures that we continue
        # sending heartbeats even if one errors
        def assertion() -> None:
            assert count_sends == 2

        await test_core.wait_for(
            assertion, timeout=datetime.timedelta(seconds=10)
        )
