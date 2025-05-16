import datetime
import typing
import unittest

import pytest

import inngest
from inngest.experimental import mocked

from .errors import UnstubbedStepError

client = inngest.Inngest(app_id="my-app")
client_mock = mocked.Inngest(app_id="test")


class TestTriggerAsync(unittest.TestCase):
    def test_parallel(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        async def fn(ctx: inngest.Context) -> tuple[str, ...]:
            return await ctx.group.parallel(
                (
                    lambda: ctx.step.run("a", lambda: "a"),
                    lambda: ctx.step.run("b", lambda: "b"),
                )
            )

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.COMPLETED
        assert res.output == ("a", "b")


class TestTriggerSync(unittest.TestCase):
    def test_no_steps(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> str:
            return "hi"

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.COMPLETED
        assert res.output == "hi"

    def test_two_steps(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> str:
            ctx.step.run("a", lambda: None)
            ctx.step.run("b", lambda: None)
            return "hi"

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.COMPLETED
        assert res.output == "hi"

    def test_client_send(self) -> None:
        """
        TODO: Figure out how to support this use case. Since the client in the
        Inngest function is real, it's trying to send the event to a real
        Inngest server.
        """

        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> list[str]:
            return client.send_sync(
                [
                    inngest.Event(name="other-event"),
                    inngest.Event(name="other-event"),
                ]
            )

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.FAILED

    def test_send_event(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> list[str]:
            return ctx.step.send_event(
                "a",
                [
                    inngest.Event(name="event-1"),
                    inngest.Event(name="event-2"),
                ],
            )

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.COMPLETED
        assert res.output == [
            "00000000000000000000000000",
            "00000000000000000000000000",
        ]

    def test_invoke(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> typing.Any:
            return ctx.step.invoke_by_id(
                "a",
                app_id="foo",
                function_id="bar",
            )

        res = mocked.trigger(
            fn,
            inngest.Event(name="test"),
            client_mock,
            step_stubs={"a": "hi"},
        )
        assert res.status is mocked.Status.COMPLETED
        assert res.output == "hi"

    def test_parallel(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> tuple[str, ...]:
            return ctx.group.parallel(
                (
                    lambda: ctx.step.run("a", lambda: "a"),
                    lambda: ctx.step.run("b", lambda: "b"),
                )
            )

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.COMPLETED
        assert res.output == ("a", "b")

    def test_sleep(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> str:
            ctx.step.sleep("a", datetime.timedelta(seconds=1))
            return "hi"

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.COMPLETED
        assert res.output == "hi"

    def test_wait_for_event(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> typing.Mapping[str, inngest.JSON]:
            event = ctx.step.wait_for_event(
                "a",
                event="other-event",
                timeout=datetime.timedelta(seconds=1),
            )
            assert event is not None
            return event.data

        res = mocked.trigger(
            fn,
            inngest.Event(name="test"),
            client_mock,
            step_stubs={
                "a": inngest.Event(data={"foo": 1}, name="other-event")
            },
        )
        assert res.status is mocked.Status.COMPLETED
        assert res.output == {"foo": 1}

    def test_wait_for_event_timeout(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            event = ctx.step.wait_for_event(
                "a",
                event="other-event",
                timeout=datetime.timedelta(seconds=1),
            )
            assert event is None

        res = mocked.trigger(
            fn,
            inngest.Event(name="test"),
            client_mock,
            step_stubs={"a": mocked.Timeout},
        )
        assert res.status is mocked.Status.COMPLETED

    def test_wait_for_event_not_stubbed(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            ctx.step.wait_for_event(
                "a",
                event="other-event",
                timeout=datetime.timedelta(seconds=1),
            )

        with pytest.raises(UnstubbedStepError):
            mocked.trigger(fn, inngest.Event(name="test"), client_mock)

    def test_retry_step(self) -> None:
        counter = 0

        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> str:
            def a() -> str:
                nonlocal counter
                counter += 1
                if counter < 2:
                    raise Exception("oh no")
                return "hi"

            return ctx.step.run("a", a)

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.COMPLETED
        assert res.output == "hi"

    def test_fail_step(self) -> None:
        @client.create_function(
            fn_id="test",
            retries=0,
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            def a() -> None:
                raise Exception("oh no")

            ctx.step.run("a", a)

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.FAILED
        assert res.output is None
        assert isinstance(res.error, Exception)
        assert str(res.error) == "oh no"

    def test_retry_fn(self) -> None:
        counter = 0

        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> str:
            nonlocal counter
            counter += 1
            if counter < 2:
                raise Exception("oh no")
            return "hi"

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.COMPLETED
        assert res.output == "hi"

    def test_fail_fn(self) -> None:
        @client.create_function(
            fn_id="test",
            retries=0,
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            raise Exception("oh no")

        res = mocked.trigger(fn, inngest.Event(name="test"), client_mock)
        assert res.status is mocked.Status.FAILED
        assert res.output is None
        assert isinstance(res.error, Exception)
        assert str(res.error) == "oh no"
