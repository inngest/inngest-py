# Sessions

## Sessions

```python
await client.send(inngest.Event(
    name="conversation/started",
    data={"user_id": "alice"},
    meta={"sessions": {"conversation": "chat-123"}},
))
```

The handler's `ctx.sessions` contains the sessions shared by every triggering event. A single-event run inherits that event's sessions; conflicting or missing keys in batches are excluded. The server allows five sessions per event. The inherited aggregate is sorted by UTF-8 key bytes and capped at five.

Client sends inside a function, `step.send_event`, and `step.invoke`/`invoke_by_id` propagate the current sessions. You can modify `ctx.sessions` before sending. Each outgoing event receives its own copy in the internal `meta.propagated_sessions` layer. Manual `meta.sessions` overrides are preserved for the server to merge:

```python
# Override one session while inheriting the others.
inngest.Event(name="child", meta={"sessions": {"conversation": "new-chat"}})
# Cut a single inherited session.
inngest.Event(name="child", meta={"sessions": {"conversation": None}})
# Clear all inherited sessions.
inngest.Event(name="child", meta={"sessions": None})
```

Omitted metadata and `sessions={}` do not override inheritance. IDs accept nonempty strings or finite numbers, normalized to JavaScript-compatible strings. Use strings for identifiers requiring exact integer precision. Boolean IDs and empty keys are rejected. Sessions group runs; they do not route chat messages, resume waits, or substitute for a run ID when scoring.

