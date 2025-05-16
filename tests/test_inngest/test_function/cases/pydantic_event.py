"""
We don't support returning Pydantic models in steps or functions. This may
change in the future.
"""

import json
import typing

import inngest
import pydantic
import test_core.helper
from inngest._internal import server_lib
from typing_extensions import assert_type

from . import base

TEvent = typing.TypeVar("TEvent", bound="BaseEvent")


class BaseEvent(pydantic.BaseModel):
    data: pydantic.BaseModel
    id: str = ""
    name: typing.ClassVar[str]
    ts: int = 0

    @classmethod
    def from_event(cls: type[TEvent], event: inngest.Event) -> TEvent:
        return cls.model_validate(event.model_dump(mode="json"))

    def to_event(self) -> inngest.Event:
        return inngest.Event(
            name=self.name,
            data=self.data.model_dump(mode="json"),
            id=self.id,
            ts=self.ts,
        )


class MyEventData(pydantic.BaseModel):
    count: int


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)

    class MyEvent(BaseEvent):
        data: MyEventData
        name = base.create_event_name(framework, test_name)

    fn_id = base.create_fn_id(test_name)
    state = base.BaseState()

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=MyEvent.name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> typing.Any:
        state.run_id = ctx.run_id
        event = MyEvent.from_event(ctx.event)
        assert_type(event, MyEvent)
        return event.model_dump(mode="json")

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=MyEvent.name),
    )
    async def fn_async(ctx: inngest.Context) -> typing.Any:
        state.run_id = ctx.run_id
        event = MyEvent.from_event(ctx.event)
        assert_type(event, MyEvent)
        return event.model_dump(mode="json")

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(MyEvent(data=MyEventData(count=1)).to_event())
        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        assert run.output is not None
        event = MyEvent.model_validate(json.loads(run.output))
        assert event.data.count == 1
        assert event.id != ""
        assert event.ts > 0

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
