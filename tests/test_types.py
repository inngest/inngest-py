"""
Even though this file has test functions, they don't actually need to run. This
file is purely for static type analysis
"""

import inngest

client = inngest.Inngest(app_id="foo", is_production=False)


def sync_fn_with_sync_step() -> None:
    """
    Test that a sync function cannot use an async step type
    """

    @client.create_function(  # type: ignore[arg-type]
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    def fn(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        pass


def async_fn_with_sync_step() -> None:
    """
    Test that an async function cannot use a sync step type
    """

    @client.create_function(  # type: ignore[arg-type]
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    async def fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        pass


def event_data_dict() -> None:
    """
    Test that event data can be a dict. This is exists to prevent a regression
    after a type fix where `Event.data` was typed as `dict[str, object]`, which
    precluded more specific types like `dict[str, str]`. That happens because
    `dict` is considered to be mutable, so type checkers make it invariant
    """

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    async def fn(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        data = {"foo": "bar"}

        await step.send_event(
            "foo",
            inngest.Event(data=data, name="foo"),
        )
