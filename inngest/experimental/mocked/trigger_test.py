import datetime
import typing
import unittest

import pytest

import inngest

from .client import Inngest
from .consts import Status, Timeout
from .errors import UnstubbedStepError
from .trigger import trigger

client = Inngest(app_id="test")


class TestTriggerAsync(unittest.TestCase):
    def test_parallel(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        async def fn(
            ctx: inngest.Context,
            step: inngest.Step,
        ) -> tuple[str, ...]:
            return await step.parallel(
                (
                    lambda: step.run("a", lambda: "a"),
                    lambda: step.run("b", lambda: "b"),
                )
            )

        res = trigger(fn, inngest.Event(name="test"), client)
        assert res.status is Status.COMPLETED
        assert res.output == ("a", "b")


class TestTriggerSync(unittest.TestCase):
    def test_no_steps(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> str:
            return "hi"

        res = trigger(fn, inngest.Event(name="test"), client)
        assert res.status is Status.COMPLETED
        assert res.output == "hi"

    def test_two_steps(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> str:
            step.run("a", lambda: None)
            step.run("b", lambda: None)
            return "hi"

        res = trigger(fn, inngest.Event(name="test"), client)
        assert res.status is Status.COMPLETED
        assert res.output == "hi"

    def test_client_send(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> list[str]:
            return client.send_sync(
                [
                    inngest.Event(name="other-event"),
                    inngest.Event(name="other-event"),
                ]
            )

        res = trigger(fn, inngest.Event(name="test"), client)
        assert res.status is Status.COMPLETED
        assert res.output == [
            "00000000000000000000000000",
            "00000000000000000000000000",
        ]

    def test_send_event(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> list[str]:
            return step.send_event(
                "a",
                [
                    inngest.Event(name="event-1"),
                    inngest.Event(name="event-2"),
                ],
            )

        res = trigger(fn, inngest.Event(name="test"), client)
        assert res.status is Status.COMPLETED
        assert res.output == [
            "00000000000000000000000000",
            "00000000000000000000000000",
        ]

    def test_invoke(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> typing.Any:
            return step.invoke_by_id(
                "a",
                app_id="foo",
                function_id="bar",
            )

        res = trigger(
            fn,
            inngest.Event(name="test"),
            client,
            step_stubs={"a": "hi"},
        )
        assert res.status is Status.COMPLETED
        assert res.output == "hi"

    def test_parallel(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> tuple[str, ...]:
            return step.parallel(
                (
                    lambda: step.run("a", lambda: "a"),
                    lambda: step.run("b", lambda: "b"),
                )
            )

        res = trigger(fn, inngest.Event(name="test"), client)
        assert res.status is Status.COMPLETED
        assert res.output == ("a", "b")

    def test_sleep(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> str:
            step.sleep("a", datetime.timedelta(seconds=1))
            return "hi"

        res = trigger(fn, inngest.Event(name="test"), client)
        assert res.status is Status.COMPLETED
        assert res.output == "hi"

    def test_wait_for_event(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> typing.Mapping[str, inngest.JSON]:
            event = step.wait_for_event(
                "a",
                event="other-event",
                timeout=datetime.timedelta(seconds=1),
            )
            assert event is not None
            return event.data

        res = trigger(
            fn,
            inngest.Event(name="test"),
            client,
            step_stubs={
                "a": inngest.Event(data={"foo": 1}, name="other-event")
            },
        )
        assert res.status is Status.COMPLETED
        assert res.output == {"foo": 1}

    def test_wait_for_event_timeout(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> None:
            event = step.wait_for_event(
                "a",
                event="other-event",
                timeout=datetime.timedelta(seconds=1),
            )
            assert event is None

        res = trigger(
            fn,
            inngest.Event(name="test"),
            client,
            step_stubs={"a": Timeout},
        )
        assert res.status is Status.COMPLETED

    def test_wait_for_event_not_stubbed(self) -> None:
        @client.create_function(
            fn_id="test",
            trigger=inngest.TriggerEvent(event="test"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> None:
            step.wait_for_event(
                "a",
                event="other-event",
                timeout=datetime.timedelta(seconds=1),
            )

        with pytest.raises(UnstubbedStepError):
            trigger(fn, inngest.Event(name="test"), client)
