from __future__ import annotations

import dataclasses
import json
import threading
import typing
import unittest

import fastapi
import inngest
import inngest.fast_api
import pydantic
import test_core
import uvicorn
from test_core import base, net


class _User(pydantic.BaseModel):
    name: str


class _TestBase(unittest.IsolatedAsyncioTestCase):
    def _sync(
        self,
        serve: typing.Callable[[fastapi.FastAPI], None],
    ) -> None:
        port = net.get_available_port()

        def start_app() -> None:
            app = fastapi.FastAPI()
            serve(app)
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")  # pyright: ignore[reportUnknownMemberType]

        app_thread = threading.Thread(daemon=True, target=start_app)
        app_thread.start()
        self.addCleanup(app_thread.join, timeout=1)
        base.register(port)


class TestFnOutput(_TestBase):
    async def test_invoke(self) -> None:
        """
        Invoke a function that returns a Pydantic object and specifies the
        output type. This should succeed because the output type is specified.
        """

        class _State(base.BaseState):
            invoke_output: list[_User] = []  # noqa: RUF012

        state = _State()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            serializer=inngest.PydanticSerializer(),
        )

        @client.create_function(
            fn_id="child",
            output_type=list[_User],
            retries=0,
            trigger=inngest.TriggerEvent(event="never"),
        )
        async def fn_child(ctx: inngest.Context) -> list[_User]:
            return [_User(name="Alice")]

        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="parent",
            output_type=list[_User],
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn_parent(ctx: inngest.Context) -> list[_User]:
            state.run_id = ctx.run_id
            state.invoke_output = await ctx.step.invoke(
                "invoke",
                function=fn_child,
            )
            return state.invoke_output

        self._sync(
            lambda app: inngest.fast_api.serve(
                app, client, [fn_child, fn_parent]
            )
        )

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.invoke_output == [_User(name="Alice")]

        assert run.output is not None
        assert json.loads(run.output) == [
            {
                "name": "Alice",
            }
        ]

    async def test_invoke_without_type(self) -> None:
        """
        Invoke a function that returns a Pydantic object without specifying
        the output type. This fails the run.
        """

        class _State(base.BaseState):
            invoke_output: list[_User] = []  # noqa: RUF012

        state = _State()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            serializer=inngest.PydanticSerializer(),
        )

        @client.create_function(
            fn_id="child",
            retries=0,
            trigger=inngest.TriggerEvent(event="never"),
        )
        async def fn_child(ctx: inngest.Context) -> list[_User]:
            return [_User(name="Alice")]

        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="parent",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn_parent(ctx: inngest.Context) -> list[_User]:
            state.run_id = ctx.run_id
            state.invoke_output = await ctx.step.invoke(
                "invoke",
                function=fn_child,
            )
            return state.invoke_output

        self._sync(
            lambda app: inngest.fast_api.serve(
                app, client, [fn_child, fn_parent]
            )
        )

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)
        assert isinstance(output, dict)
        assert output["message"] == "returned unserializable data"
        assert output["name"] == "OutputUnserializableError"

    async def test_fn_output_without_serializer(self) -> None:
        """
        Return a Pydantic object without a serializer. This fails the run.
        """

        state = test_core.BaseState()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )

        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="parent",
            output_type=list[_User],
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> list[_User]:
            state.run_id = ctx.run_id
            return [_User(name="Alice")]

        self._sync(lambda app: inngest.fast_api.serve(app, client, [fn]))

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)
        assert isinstance(output, dict)
        assert output["message"] == "returned unserializable data"
        assert output["name"] == "OutputUnserializableError"


class TestStepOutput(_TestBase):
    async def test_run(self) -> None:
        """
        Ensure a variety of return types work.
        """

        class _State(base.BaseState):
            step_object_output: _User | None = None
            step_none_output: _User | None = None
            step_list_output: list[_User] | None = None
            step_primitive_output: int | None = None

        state = _State()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            serializer=inngest.PydanticSerializer(),
        )

        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="parent",
            output_type=list[_User],
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id

            async def step_object(name: str) -> _User:
                return _User(name=name)

            state.step_object_output = await ctx.step.run(
                "object",
                step_object,
                "Alice",
                output_type=_User,
            )

            async def step_none() -> _User | None:
                return None

            state.step_none_output = await ctx.step.run(
                "none",
                step_none,
                output_type=_User | None,
            )

            async def step_list() -> list[_User]:
                return [_User(name="Alice")]

            state.step_list_output = await ctx.step.run(
                "list",
                step_list,
                output_type=list[_User],
            )

            async def step_primitive() -> int:
                return 1

            state.step_primitive_output = await ctx.step.run(
                "primitive",
                step_primitive,
            )

        self._sync(lambda app: inngest.fast_api.serve(app, client, [fn]))

        await client.send(inngest.Event(name=event_name))

        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        assert isinstance(state.step_object_output, _User)
        assert state.step_object_output.name == "Alice"

        assert state.step_none_output is None

        assert isinstance(state.step_list_output, list)
        assert len(state.step_list_output) == 1
        assert isinstance(state.step_list_output[0], _User)
        assert state.step_list_output[0].name == "Alice"
        assert state.step_primitive_output == 1

    async def test_without_serializer(self) -> None:
        """
        Return a Pydantic object without a serializer. This fails the run.
        """

        class _State(base.BaseState):
            step_output: object = None

        state = _State()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )

        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="parent",
            output_type=_User,
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id

            async def step_object(name: str) -> _User:
                return _User(name=name)

            state.step_output = await ctx.step.run("a", step_object, "Alice")

        self._sync(lambda app: inngest.fast_api.serve(app, client, [fn]))

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)
        assert isinstance(output, dict)
        assert output["message"] == '"a" returned unserializable data'
        assert output["name"] == "OutputUnserializableError"

    async def test_without_type(self) -> None:
        """
        Return a Pydantic object without specifying the output type. This fails
        the run.
        """

        class _State(base.BaseState):
            step_output: _User | None = None

        state = _State()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            serializer=inngest.PydanticSerializer(),
        )

        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="parent",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id

            async def step_object(name: str) -> _User:
                return _User(name=name)

            state.step_output = await ctx.step.run("a", step_object, "Alice")

        self._sync(lambda app: inngest.fast_api.serve(app, client, [fn]))

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)
        assert isinstance(output, dict)
        assert output["message"] == '"a" returned unserializable data'
        assert output["name"] == "OutputUnserializableError"


class TestStepSendEvent(_TestBase):
    async def test(self) -> None:
        """
        Ensure that step.send_event works. This is a regression test created
        because of a deserialization bug
        """

        state = base.BaseState()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            serializer=inngest.PydanticSerializer(),
        )

        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id

            await ctx.step.send_event(
                "send",
                events=[
                    inngest.Event(
                        name=test_core.random_suffix("event-2"),
                        data={"name": "Alice"},
                    )
                ],
            )

        self._sync(lambda app: inngest.fast_api.serve(app, client, [fn]))

        await client.send(inngest.Event(name=event_name))

        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )


class TestOnFailure(_TestBase):
    async def test_success(self) -> None:
        """
        When a serializer is provided, on_failure handlers can return Pydantic
        objects. No output type is necessary.
        """

        state = base.BaseState()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            serializer=inngest.PydanticSerializer(),
        )

        event_name = test_core.random_suffix("event")

        async def on_failure(ctx: inngest.Context) -> list[_User]:
            state.run_id = ctx.run_id
            return [_User(name="Alice")]

        @client.create_function(
            fn_id="parent",
            on_failure=on_failure,
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            raise Exception("oh no")

        self._sync(lambda app: inngest.fast_api.serve(app, client, [fn]))

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        assert run.output is not None
        assert json.loads(run.output) == [
            {
                "name": "Alice",
            }
        ]

    async def test_without_serializer(self) -> None:
        """
        Return a Pydantic object without a serializer. This fails the run.
        """

        state = base.BaseState()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
        )

        event_name = test_core.random_suffix("event")

        async def on_failure(ctx: inngest.Context) -> list[_User]:
            state.run_id = ctx.run_id
            return [_User(name="Alice")]

        @client.create_function(
            fn_id="parent",
            on_failure=on_failure,
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn(ctx: inngest.Context) -> None:
            raise Exception("oh no")

        self._sync(lambda app: inngest.fast_api.serve(app, client, [fn]))

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)
        assert isinstance(output, dict)
        assert output["message"] == "returned unserializable data"
        assert output["name"] == "OutputUnserializableError"


class TestCustomSerializer(_TestBase):
    async def test_invoke(self) -> None:
        """
        Custom serializers work. This test will use a custom dataclass
        serializer.
        """

        @dataclasses.dataclass
        class _Animal:
            name: str

            @classmethod
            def from_dict(cls, data: dict[str, object]) -> _User:
                return cls(**data)  # type: ignore

        class CustomSerializer(inngest.Serializer):
            def serialize(self, obj: object, typ: object) -> object:
                return dataclasses.asdict(obj)  # type: ignore

            def deserialize(self, obj: object, typ: object) -> object:
                return typ.from_dict(obj)  # type: ignore

        class _State(base.BaseState):
            invoke_output: _Animal = _Animal(name="")

        state = _State()

        client = inngest.Inngest(
            app_id=test_core.random_suffix("app"),
            is_production=False,
            serializer=CustomSerializer(),
        )

        @client.create_function(
            fn_id="child",
            output_type=_Animal,
            retries=0,
            trigger=inngest.TriggerEvent(event="never"),
        )
        async def fn_child(ctx: inngest.Context) -> _Animal:
            return _Animal(name="Baxter")

        event_name = test_core.random_suffix("event")

        @client.create_function(
            fn_id="parent",
            output_type=_Animal,
            retries=0,
            trigger=inngest.TriggerEvent(event=event_name),
        )
        async def fn_parent(ctx: inngest.Context) -> _Animal:
            state.run_id = ctx.run_id
            state.invoke_output = await ctx.step.invoke(
                "invoke",
                function=fn_child,
            )
            return state.invoke_output

        self._sync(
            lambda app: inngest.fast_api.serve(
                app, client, [fn_child, fn_parent]
            )
        )

        await client.send(inngest.Event(name=event_name))

        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.invoke_output == _Animal(name="Baxter")
        assert run.output is not None
        assert json.loads(run.output) == {"name": "Baxter"}
