"""
Even though this file has test functions, they don't actually need to run. This
file is purely for static type analysis
"""

import functools
import typing

from typing_extensions import assert_type

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


def step_callback_Args() -> None:
    """
    Ensure that step callback arguments are correctly typed. They're inferred
    from the step callback's type signature.
    """

    async def step_callback_async(a: int, b: str) -> bool:
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
        assert_type(output, bool)

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
        assert_type(output, bool)

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
        assert_type(output, bool)


def step_callback_kwargs() -> None:
    """
    Step callback kwargs require functools.partial.
    """

    async def step_callback_async(a: int, *, b: str) -> bool:
        return True

    def step_callback_sync(a: int, *, b: str) -> bool:
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

        output = await step.run(
            "step",
            functools.partial(step_callback_async, 1, b="a"),
        )
        assert_type(output, bool)

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

        output = await step.run(
            "step",
            functools.partial(step_callback_sync, 1, b="a"),
        )
        assert_type(output, bool)

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

        output = step.run(
            "step",
            functools.partial(step_callback_sync, 1, b="a"),
        )
        assert_type(output, bool)


def parallel() -> None:
    """
    Specify parallel steps "inline" (i.e. not using an iterator).
    """

    async def fn_1_async() -> int:
        return 1

    def fn_1_sync() -> int:
        return 1

    async def fn_2_async(a: int, *, b: str) -> str:
        return "a"

    def fn_2_sync(a: int, *, b: str) -> str:
        return "a"

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    async def async_fn(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        output = await step.parallel(
            (
                functools.partial(step.run, "step-1", fn_1_async),
                functools.partial(
                    step.run,
                    "step-2",
                    functools.partial(fn_2_async, 1, b="a"),
                ),
                functools.partial(step.sleep, "sleep", 1),
            )
        )

        # Type is wrong because of a mypy limitation around inferring union
        # types from tuples
        assert_type(output, tuple[None, ...])

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    def sync_fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        output = step.parallel(
            (
                functools.partial(step.run, "step-1", fn_1_sync),
                functools.partial(
                    step.run,
                    "step-2",
                    functools.partial(fn_2_sync, 1, b="a"),
                ),
                functools.partial(step.sleep, "sleep", 1),
            )
        )

        # Type is wrong because of a mypy limitation around inferring union
        # types from tuples
        assert_type(output, tuple[None, ...])


def parallel_iterator() -> None:
    """
    Specify parallel steps by iterating over a list.
    """

    async def step_callback_async(a: int, *, b: str) -> bool:
        return True

    def step_callback_sync(a: int, *, b: str) -> bool:
        return True

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    async def async_fn(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        items = [1, 2, 3]

        # The tuple must have an explicit type since nested functools.partial
        # calls have trouble with generics
        steps = tuple[typing.Callable[[], typing.Awaitable[bool]], ...](
            functools.partial(
                step.run,
                "step",
                functools.partial(step_callback_async, item, b="a"),
            )
            for item in items
        )

        output = await step.parallel(steps)
        assert_type(output, tuple[bool, ...])

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    def sync_fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        items = [1, 2, 3]

        # The tuple must have an explicit type since nested functools.partial
        # calls have trouble with generics
        steps = tuple[typing.Callable[[], bool], ...](
            functools.partial(
                step.run,
                "step",
                functools.partial(step_callback_sync, item, b="a"),
            )
            for item in items
        )

        output = step.parallel(steps)
        assert_type(output, tuple[bool, ...])
