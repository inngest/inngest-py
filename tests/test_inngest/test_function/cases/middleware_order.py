"""
Test that middleware classes are called in the correct order.

TODO: In v0.5, we should reverse middleware order for the "after" hooks.
"""

import inspect

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    def __init__(self) -> None:
        self.results: list[inngest.TransformOutputResult] = []
        self.messages: list[str] = []


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    class Sync1(_MwSyncBase):
        def append_message(self, message: str) -> None:
            state.messages.append(message)

    class Sync2(_MwSyncBase):
        def append_message(self, message: str) -> None:
            state.messages.append(message)

    class Async1(_MwAsyncBase):
        def append_message(self, message: str) -> None:
            state.messages.append(message)

    class Async2(_MwAsyncBase):
        def append_message(self, message: str) -> None:
            state.messages.append(message)

    @client.create_function(
        fn_id=fn_id,
        middleware=[Sync1, Sync2],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id

        step.send_event("a", inngest.Event(name="never"))

    @client.create_function(
        fn_id=fn_id,
        middleware=[Async1, Async2],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id

        await step.send_event("a", inngest.Event(name="never"))

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        _assert_messages(
            is_sync,
            state.messages,
            [
                "1.transform_input",
                "2.transform_input",
                "1.before_memoization",
                "2.before_memoization",
                "1.after_memoization",
                "2.after_memoization",
                "1.before_execution",
                "2.before_execution",
                "1.before_send_events",
                "2.before_send_events",
                "1.after_send_events",
                "2.after_send_events",
                "1.after_execution",
                "2.after_execution",
                "1.transform_output",
                "2.transform_output",
                "1.before_response",
                "2.before_response",
                "1.transform_input",
                "2.transform_input",
                "1.before_memoization",
                "2.before_memoization",
                "1.after_memoization",
                "2.after_memoization",
                "1.before_execution",
                "2.before_execution",
                "1.after_execution",
                "2.after_execution",
                "1.transform_output",
                "2.transform_output",
                "1.before_response",
                "2.before_response",
            ],
        )

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )


def _assert_messages(
    is_sync: bool,
    actual: list[str],
    expected: list[str],
) -> None:
    prefix = "Sync" if is_sync else "Async"
    expected = [f"{prefix}{m}" for m in expected]
    assert actual == expected


class _MwSyncBase(inngest.MiddlewareSync):
    def append_message(self, message: str) -> None:
        raise NotImplementedError()

    def after_execution(self) -> None:
        self.append_message(_get_method_name())

    def after_memoization(self) -> None:
        self.append_message(_get_method_name())

    def after_send_events(
        self,
        result: inngest.SendEventsResult,
    ) -> None:
        self.append_message(_get_method_name())

    def before_execution(self) -> None:
        self.append_message(_get_method_name())

    def before_memoization(self) -> None:
        self.append_message(_get_method_name())

    def before_response(self) -> None:
        self.append_message(_get_method_name())

    def before_send_events(self, events: list[inngest.Event]) -> None:
        self.append_message(_get_method_name())

    def transform_input(
        self,
        ctx: inngest.Context,
        function: inngest.Function,
        steps: inngest.StepMemos,
    ) -> None:
        self.append_message(_get_method_name())

    def transform_output(
        self,
        result: inngest.TransformOutputResult,
    ) -> None:
        self.append_message(_get_method_name())


class _MwAsyncBase(inngest.Middleware):
    def append_message(self, message: str) -> None:
        raise NotImplementedError()

    async def after_execution(self) -> None:
        self.append_message(_get_method_name())

    async def after_memoization(self) -> None:
        self.append_message(_get_method_name())

    async def after_send_events(
        self,
        result: inngest.SendEventsResult,
    ) -> None:
        self.append_message(_get_method_name())

    async def before_execution(self) -> None:
        self.append_message(_get_method_name())

    async def before_memoization(self) -> None:
        self.append_message(_get_method_name())

    async def before_response(self) -> None:
        self.append_message(_get_method_name())

    async def before_send_events(self, events: list[inngest.Event]) -> None:
        self.append_message(_get_method_name())

    async def transform_input(
        self,
        ctx: inngest.Context,
        function: inngest.Function,
        steps: inngest.StepMemos,
    ) -> None:
        self.append_message(_get_method_name())

    async def transform_output(
        self,
        result: inngest.TransformOutputResult,
    ) -> None:
        self.append_message(_get_method_name())


def _get_method_name() -> str:
    frame = inspect.currentframe()
    assert frame is not None
    frame = frame.f_back
    assert frame is not None
    class_name = frame.f_locals["self"].__class__.__name__
    method_name = frame.f_code.co_name
    return f"{class_name}.{method_name}"
