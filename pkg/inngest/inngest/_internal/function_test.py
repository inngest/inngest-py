import pytest

import inngest
from inngest._internal import errors


def test_sync_fn_with_async_on_failure() -> None:
    """
    Test that a sync function can not have an async on_failure handler.
    """

    client = inngest.Inngest(app_id="test", is_production=False)

    async def on_failure(ctx: inngest.Context) -> None:
        pass

    with pytest.raises(errors.Error):

        @client.create_function(
            fn_id="foo",
            trigger=inngest.TriggerEvent(event="foo"),
            on_failure=on_failure,
        )
        def fn(ctx: inngest.ContextSync) -> None:
            pass


def test_async_fn_with_sync_on_failure() -> None:
    """
    Test that an async function can not have a sync on_failure handler.
    """

    client = inngest.Inngest(app_id="test", is_production=False)

    def on_failure(ctx: inngest.ContextSync) -> None:
        pass

    with pytest.raises(errors.Error):

        @client.create_function(
            fn_id="foo",
            trigger=inngest.TriggerEvent(event="foo"),
            on_failure=on_failure,
        )
        async def fn(ctx: inngest.Context) -> None:
            pass
