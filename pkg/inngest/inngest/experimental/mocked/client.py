from __future__ import annotations

import collections.abc

import inngest
from inngest._internal import server_lib


class Inngest(inngest.Inngest):
    """
    Mock Inngest client.
    """

    async def send(
        self,
        events: server_lib.Event | collections.abc.Sequence[server_lib.Event],
        *,
        skip_middleware: bool = False,
    ) -> list[str]:
        """
        Mocked event send method.
        """

        if isinstance(events, server_lib.Event):
            _events = [events]
        elif isinstance(events, (list, tuple)):
            _events = list(events)
        elif isinstance(events, collections.abc.Sequence) and not isinstance(
            events, (str, bytes)
        ):
            _events = list(events)
        else:
            _events = [events]

        ids = []
        for _ in _events:
            ids.append("00000000000000000000000000")
        return ids

    def send_sync(
        self,
        events: server_lib.Event | collections.abc.Sequence[server_lib.Event],
        *,
        skip_middleware: bool = False,
    ) -> list[str]:
        """
        Mocked event send method.
        """

        if isinstance(events, server_lib.Event):
            _events = [events]
        elif isinstance(events, (list, tuple)):
            _events = list(events)
        elif isinstance(events, collections.abc.Sequence) and not isinstance(
            events, (str, bytes)
        ):
            _events = list(events)
        else:
            _events = [events]

        ids = []
        for _ in _events:
            ids.append("00000000000000000000000000")
        return ids
