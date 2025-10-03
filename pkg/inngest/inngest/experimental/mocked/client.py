from __future__ import annotations

import inngest
from inngest._internal import server_lib


class Inngest(inngest.Inngest):
    """
    Mock Inngest client.
    """

    async def send(
        self,
        events: server_lib.Event | list[server_lib.Event],
        *,
        skip_middleware: bool = False,
    ) -> list[str]:
        """
        Mocked event send method.
        """

        ids = []
        for event in events:
            ids.append("00000000000000000000000000")
        return ids

    def send_sync(
        self,
        events: server_lib.Event | list[server_lib.Event],
        *,
        skip_middleware: bool = False,
    ) -> list[str]:
        """
        Mocked event send method.
        """

        ids = []
        for event in events:
            ids.append("00000000000000000000000000")
        return ids
