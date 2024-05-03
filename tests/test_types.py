"""
Even though this file has test functions, they don't actually need to run. This
file is purely for static type analysis
"""

import typing

import inngest

_T = typing.TypeVar("_T")


class _AssertType(typing.Generic[_T]):
    """
    Used to assert type hints. A no-op at runtime.
    """

    def __init__(self, value: _T) -> None:
        pass


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


def step_callback_Args() -> None:
    """
    Ensure that step callback arguments are correctly typed. They're inferred
    from the step callback's type signature.
    """

    def step_callback_async(a: int, b: str) -> bool:
        return True

    def step_callback_sync(a: int, b: str) -> bool:
        return True

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    async def async_fn(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        # Incorrect arg types fail type checker
        await step.run(
            "step",
            step_callback_async,  # type: ignore[arg-type]
            "a",
            1,
        )  # type: ignore[call-arg]

        output = await step.run("step", step_callback_async, 1, "a")

        # Output type is correctly inferred
        _AssertType[bool](output)
        _AssertType[str](output)  # type: ignore[arg-type]

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    async def async_fn_with_sync_callback(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        # Incorrect arg types fail type checker
        await step.run(
            "step",
            step_callback_sync,  # type: ignore[arg-type]
            "a",
            1,
        )  # type: ignore[call-arg]

        output = await step.run("step", step_callback_sync, 1, "a")

        # Output type is correctly inferred
        _AssertType[bool](output)
        _AssertType[str](output)  # type: ignore[arg-type]

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    def sync_fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        # Incorrect arg types fail type checker
        step.run(
            "step",
            step_callback_sync,  # type: ignore[arg-type]
            "a",
            1,
        )

        output = step.run("step", step_callback_sync, 1, "a")

        # Output type is correctly inferred
        _AssertType[bool](output)
        _AssertType[str](output)  # type: ignore[arg-type]
