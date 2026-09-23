import unittest

import pytest

from inngest import Inngest
from inngest.experimental.realtime.subscription_tokens import (
    get_subscription_token,
    get_subscription_token_sync,
)


class TestSubscriptionTokens(unittest.IsolatedAsyncioTestCase):
    def test_reject_bare_string_topics(self) -> None:
        client = Inngest(app_id="test-app")

        with pytest.raises(
            TypeError, match="topics must be a sequence of strings"
        ):
            get_subscription_token_sync(
                client=client,
                channel="test-channel",
                topics="bare-string",  # type: ignore[arg-type]
            )

    async def test_reject_bare_string_topics_async(self) -> None:
        client = Inngest(app_id="test-app")

        with pytest.raises(
            TypeError, match="topics must be a sequence of strings"
        ):
            await get_subscription_token(
                client=client,
                channel="test-channel",
                topics="bare-string",  # type: ignore[arg-type]
            )
