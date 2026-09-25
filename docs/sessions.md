# Sessions

Sessions group related function runs in the dashboard, such as runs belonging to
one conversation or user. They do not route messages, resume waits, or replace a
function run ID.

Attach a session to the starting event. A handler's `ctx.sessions` then propagates
to child events automatically:

```python
import inngest

client = inngest.Inngest(app_id="conversations")


@client.create_function(
    fn_id="parent",
    trigger=inngest.TriggerEvent(event="conversation/started"),
)
async def parent(ctx: inngest.Context) -> None:
    # The incoming event supplies {"conversation": "chat-123"}.
    await ctx.step.send_event("send-child", inngest.Event(name="conversation/child"))


@client.create_function(
    fn_id="child",
    trigger=inngest.TriggerEvent(event="conversation/child"),
)
async def child(ctx: inngest.Context) -> dict[str, str]:
    return ctx.sessions  # {"conversation": "chat-123"}


async def start_conversation() -> None:
    await client.send(inngest.Event(
        name="conversation/started",
        meta={"sessions": {"conversation": "chat-123"}},
    ))
```

Register both handlers with your framework's Inngest adapter, then call
`start_conversation()`. Sync handlers use `ContextSync`, `client.send_sync`, and
step methods without `await`.

`ctx.sessions` is initialized once when the execution context is constructed and
remains mutable. Changing it affects subsequent sends. `step.send_event`,
`step.invoke`/`invoke_by_id`, and client sends inside a handler all propagate its
current values. Client sends outside execution have no implicit sessions.

## Override inherited sessions

Set `meta.sessions` on a child event (or `meta` on an invoke) to control inheritance.
Assuming the parent has `{"conversation": "chat-123", "user": "alice"}`:

| Child `meta.sessions` | Sessions resolved by the server |
| --- | --- |
| Omitted | Both parent sessions |
| `{}` | Both parent sessions |
| `None` | No sessions |
| `{"conversation": None}` | Only `user=alice` |
| `{"conversation": "chat-456"}` | `conversation=chat-456` and `user=alice` |

`None` is a *tombstone*: an explicit removal instruction. A whole-field tombstone
removes all inherited sessions; a per-key tombstone removes just that key.

IDs can be nonempty strings or finite numbers. Numbers are normalized to
JavaScript-compatible strings; use strings for identifiers requiring exact integer
precision. Boolean IDs, empty IDs, and empty keys are rejected.

## Batches and server responsibilities

The server resolves incoming metadata before invoking the SDK. The SDK reads the
resolved `meta.sessions` and initializes `ctx.sessions` with only the key/value
pairs shared by **every** triggering event. Conflicting values and keys missing
from any event are excluded. The inherited aggregate is sorted by UTF-8 key bytes
and capped at five sessions.

On outgoing events, the SDK copies current context sessions into the internal
`meta.propagated_sessions` layer and preserves explicit `meta.sessions` overrides.
It does not merge these layers. The server applies overrides and tombstones to
produce the resolved sessions for the next function.

Step sends stamp propagation before send middleware runs. The client preserves
that stamp when sending the step's events, including edits made by middleware.
Direct client sends also stamp before their send middleware. Each event receives
independent metadata; payload objects are not deep-copied.

Event construction validates session metadata. Sends validate and normalize it
again after middleware, when building the HTTP payload; invokes do so when
building their invoke payload. This final check does not mutate the caller's
metadata. Ordinary `model_dump` and `model_dump_json` use Pydantic's standard
serialization behavior.

The execution-local session binding covers handlers and the `transform_input`,
`before_execution`, and `after_execution` hooks, plus send hooks called during
execution. It is reset before `transform_output` and `before_response`, including
on failure. Sends from those response hooks do not implicitly inherit the run's
sessions.
