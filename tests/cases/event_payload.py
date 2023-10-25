import inngest

from .base import BaseState, Case, wait_for


class _State(BaseState):
    event: inngest.Event | None = None

    def is_done(self) -> bool:
        return self.event is not None


def create(client: inngest.Inngest, framework: str) -> Case:
    name = "event_payload"
    event_name = f"{framework}/{name}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(id=name),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, event: inngest.Event, **_kwargs: object) -> None:
        state.event = event

    def run_test(_self: object) -> None:
        client.send(
            inngest.Event(
                data={"foo": {"bar": "baz"}},
                name=event_name,
                user={"a": {"b": "c"}},
            )
        )

        def assertion() -> None:
            assert state.event is not None
            assert state.event.id != ""
            assert state.event.name == event_name
            assert state.event.data == {"foo": {"bar": "baz"}}
            assert state.event.ts > 0
            assert state.event.user == {"a": {"b": "c"}}

        wait_for(assertion)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=name,
    )
