import inngest
import tests.helper

from . import base

_TEST_NAME = "event_payload"


class _State(base.BaseState):
    event: inngest.Event | None = None


def create(
    client: inngest.Inngest,
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = _State()

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        *, event: inngest.Event, run_id: str, **_kwargs: object
    ) -> None:
        state.event = event
        state.run_id = run_id

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        *, event: inngest.Event, run_id: str, **_kwargs: object
    ) -> None:
        state.event = event
        state.run_id = run_id

    def run_test(_self: object) -> None:
        client.send_sync(
            inngest.Event(
                data={"foo": {"bar": "baz"}},
                name=event_name,
                user={"a": {"b": "c"}},
            )
        )
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.event is not None
        assert state.event.id != ""
        assert state.event.name == event_name
        assert state.event.data == {"foo": {"bar": "baz"}}
        assert state.event.ts > 0
        assert state.event.user == {"a": {"b": "c"}}

    fn: inngest.Function
    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=test_name,
    )
