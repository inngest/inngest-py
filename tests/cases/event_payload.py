import inngest
import tests.helper

from . import base

_TEST_NAME = "event_payload"


class _State(base.BaseState):
    event: inngest.Event | None = None


def create(client: inngest.Inngest, framework: str) -> base.Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(id=_TEST_NAME),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, event: inngest.Event, run_id: str, **_kwargs: object) -> None:
        state.event = event
        state.run_id = run_id

    def run_test(_self: object) -> None:
        client.send(
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

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
