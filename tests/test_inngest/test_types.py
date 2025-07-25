# pyright: reportUnusedFunction=false

"""
Even though this file has test functions, they don't actually need to run. This
file is purely for static type analysis
"""

import functools
import typing

import inngest
from typing_extensions import assert_type

client = inngest.Inngest(app_id="foo", is_production=False)


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
    async def fn(ctx: inngest.Context) -> None:
        data = {"foo": "bar"}

        await ctx.step.send_event(
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
    async def async_fn(ctx: inngest.Context) -> None:
        # Incorrect arg types fail type checker
        await ctx.step.run(
            "step",
            step_callback_async,  # type: ignore[arg-type]
            "a",
            1,
        )

        output = await ctx.step.run("step", step_callback_async, 1, "a")
        assert_type(output, bool)

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    async def async_fn_with_sync_callback(ctx: inngest.Context) -> None:
        # Incorrect arg types fail type checker
        await ctx.step.run(
            "step",
            step_callback_sync,  # type: ignore[arg-type]
            "a",
            1,
        )

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    def sync_fn(ctx: inngest.ContextSync) -> None:
        # Incorrect arg types fail type checker
        ctx.step.run(
            "step",
            step_callback_sync,  # type: ignore[arg-type]
            "a",
            1,
        )

        output = ctx.step.run("step", step_callback_sync, 1, "a")
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
    async def async_fn(ctx: inngest.Context) -> None:
        # Incorrect arg types fail type checker
        await ctx.step.run(
            "step",
            step_callback_async,  # type: ignore[arg-type]
            "a",
            1,
        )

        output = await ctx.step.run(
            "step",
            functools.partial(step_callback_async, 1, b="a"),
        )
        assert_type(output, bool)

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    async def async_fn_with_sync_callback(ctx: inngest.Context) -> None:
        # Incorrect arg types fail type checker
        await ctx.step.run(
            "step",
            step_callback_sync,  # type: ignore[arg-type]
            "a",
            1,
        )

        await ctx.step.run(
            "step",
            functools.partial(step_callback_sync, 1, b="a"),  # type: ignore[arg-type]
        )

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    def sync_fn(ctx: inngest.ContextSync) -> None:
        # Incorrect arg types fail type checker
        ctx.step.run(
            "step",
            step_callback_sync,  # type: ignore[arg-type]
            "a",
            1,
        )

        output = ctx.step.run(
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
    async def async_fn(ctx: inngest.Context) -> None:
        await ctx.group.parallel(
            (
                functools.partial(ctx.step.run, "step-1", fn_1_async),
                functools.partial(
                    ctx.step.run,
                    "step-2",
                    functools.partial(fn_2_async, 1, b="a"),
                ),
                functools.partial(ctx.step.sleep, "sleep", 1),
            )
        )

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    def sync_fn(ctx: inngest.ContextSync) -> None:
        ctx.group.parallel(
            (
                functools.partial(ctx.step.run, "step-1", fn_1_sync),
                functools.partial(
                    ctx.step.run,
                    "step-2",
                    functools.partial(fn_2_sync, 1, b="a"),
                ),
                functools.partial(ctx.step.sleep, "sleep", 1),
            )
        )


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
    async def async_fn(ctx: inngest.Context) -> None:
        items = [1, 2, 3]

        # The tuple must have an explicit type since nested functools.partial
        # calls have trouble with generics
        steps = tuple[typing.Callable[[], typing.Awaitable[bool]], ...](
            functools.partial(
                ctx.step.run,
                "step",
                functools.partial(step_callback_async, item, b="a"),
            )
            for item in items
        )

        output = await ctx.group.parallel(steps)
        assert_type(output, tuple[bool, ...])

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    def sync_fn(ctx: inngest.ContextSync) -> None:
        items = [1, 2, 3]

        # The tuple must have an explicit type since nested functools.partial
        # calls have trouble with generics
        steps = tuple[typing.Callable[[], bool], ...](
            functools.partial(
                ctx.step.run,
                "step",
                functools.partial(step_callback_sync, item, b="a"),
            )
            for item in items
        )

        output = ctx.group.parallel(steps)
        assert_type(output, tuple[bool, ...])


def step_return_types() -> None:
    """
    Test that a sync function cannot use an async step type
    """

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    async def fn(ctx: inngest.Context) -> None:
        async def fn_bool() -> bool:
            return True

        assert_type(await ctx.step.run("fn_bool", fn_bool), bool)

        async def fn_int() -> int:
            return 1

        assert_type(await ctx.step.run("fn_int", fn_int), int)

        async def fn_float() -> float:
            return 1.0

        assert_type(await ctx.step.run("fn_float", fn_float), float)

        async def fn_str() -> str:
            return "foo"

        assert_type(await ctx.step.run("fn_str", fn_str), str)

        async def fn_dict() -> dict[str, int]:
            return {"foo": 1}

        assert_type(await ctx.step.run("fn_dict", fn_dict), dict[str, int])

        class MyTypedDict(typing.TypedDict):
            foo: str

        async def fn_typed_dict() -> MyTypedDict:
            return {"foo": "bar"}

        assert_type(
            await ctx.step.run("fn_typed_dict", fn_typed_dict), MyTypedDict
        )

        async def fn_list() -> list[dict[str, int]]:
            return [{"foo": 1}]

        assert_type(
            await ctx.step.run("fn_list", fn_list), list[dict[str, int]]
        )

        async def fn_none() -> None:
            return None

        assert_type(await ctx.step.run("fn_none", fn_none), None)

    @client.create_function(
        fn_id="foo",
        trigger=inngest.TriggerEvent(event="foo"),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        def fn_bool() -> bool:
            return True

        assert_type(ctx.step.run("fn_bool", fn_bool), bool)

        def fn_int() -> int:
            return 1

        assert_type(ctx.step.run("fn_int", fn_int), int)

        def fn_float() -> float:
            return 1.0

        assert_type(ctx.step.run("fn_float", fn_float), float)

        def fn_str() -> str:
            return "foo"

        assert_type(ctx.step.run("fn_str", fn_str), str)

        def fn_dict() -> dict[str, int]:
            return {"foo": 1}

        assert_type(ctx.step.run("fn_dict", fn_dict), dict[str, int])

        class MyTypedDict(typing.TypedDict):
            foo: str

        def fn_typed_dict() -> MyTypedDict:
            return {"foo": "bar"}

        assert_type(ctx.step.run("fn_typed_dict", fn_typed_dict), MyTypedDict)

        def fn_list() -> list[dict[str, int]]:
            return [{"foo": 1}]

        assert_type(ctx.step.run("fn_list", fn_list), list[dict[str, int]])

        def fn_none() -> None:
            return None

        assert_type(ctx.step.run("fn_none", fn_none), None)
