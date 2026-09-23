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

    with pytest.raises(errors.Error) as e:

        @client.create_function(
            fn_id="foo",
            trigger=inngest.TriggerEvent(event="foo"),
            on_failure=on_failure,
        )
        def fn(ctx: inngest.ContextSync) -> None:
            pass

    assert (
        str(e.value)
        == "a non-async function cannot have an async on_failure handler (function foo)"
    )


def test_async_fn_with_sync_on_failure() -> None:
    """
    Test that an async function can not have a sync on_failure handler.
    """

    client = inngest.Inngest(app_id="test", is_production=False)

    def on_failure(ctx: inngest.ContextSync) -> None:
        pass

    with pytest.raises(errors.Error) as e:

        @client.create_function(
            fn_id="foo",
            trigger=inngest.TriggerEvent(event="foo"),
            on_failure=on_failure,
        )
        async def fn(ctx: inngest.Context) -> None:
            pass

    assert (
        str(e.value)
        == "an async function cannot have a non-async on_failure handler (function foo)"
    )


def test_create_function_with_sequence_triggers() -> None:
    """
    Test that create_function accepts homogeneous list of TriggerEvent,
    tuples, and generic sequences without type errors or runtime issues.
    """
    client = inngest.Inngest(app_id="test", is_production=False)

    # 1. List of TriggerEvent (issue #305)
    triggers_list: list[inngest.TriggerEvent] = [
        inngest.TriggerEvent(event="app/user.created"),
        inngest.TriggerEvent(event="app/user.updated"),
    ]

    @client.create_function(
        fn_id="handle-user-events",
        trigger=triggers_list,
    )
    async def fn_with_list(ctx: inngest.Context) -> None:
        pass

    assert len(fn_with_list._triggers) == 2

    # 2. Tuple of triggers
    triggers_tuple = (
        inngest.TriggerEvent(event="app/order.placed"),
        inngest.TriggerCron(cron="0 * * * *"),
    )

    @client.create_function(
        fn_id="handle-order-events",
        trigger=triggers_tuple,
    )
    async def fn_with_tuple(ctx: inngest.Context) -> None:
        pass

    assert len(fn_with_tuple._triggers) == 2

    # 3. Sequence of cancel and concurrency
    cancel_list = [
        inngest.Cancel(
            event="app/user.deleted",
            if_exp="async.data.user_id == event.data.user_id",
        )
    ]
    concurrency_tuple = (
        inngest.Concurrency(
            limit=5,
            key="event.data.user_id",
        ),
    )

    @client.create_function(
        fn_id="handle-user-cancel",
        trigger=inngest.TriggerEvent(event="app/user.created"),
        cancel=cancel_list,
        concurrency=concurrency_tuple,
    )
    async def fn_with_configs(ctx: inngest.Context) -> None:
        pass

    assert fn_with_configs._opts.cancel == cancel_list
    assert fn_with_configs._opts.concurrency == concurrency_tuple

