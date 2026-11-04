# Spans

Spans are experimental and internal, like the TypeScript SDK's. `ctx.group._span` groups the steps discovered inside a `with` block under one span in the run's trace, nested in any enclosing span. Usage and semantics are in the `Group._span` docstring (`step_lib/group.py`).

It mirrors the TypeScript SDK's `group["~span"]` and uses the same wire format.

## Wire format

Each step inside a span reports `opts.span`, the span path outermost-first, and `opts.origin` when the innermost span has one:

```json
{
  "span": [
    {"id": "agent", "name": "Research agent", "kind": "agent"},
    {"id": "llm", "name": "llm", "kind": "llm"}
  ]
}
```

`kind` and `origin` are omitted when unset. A step's own `origin` wins over the span's. Spans and steps inside a span with an `origin` inherit it, so the Inngest UI can de-emphasize library-run steps.

## Implementation notes

`Group._span` and `GroupSync._span` return a `run_context.SpanScope`. `run_context.prepare_step` stamps the path onto each step during discovery. Sandboxes use `SpanScope` directly.

`inngest_langchain` uses `_span` for its agent, model and tool spans, and sets `origin` on the model and tool spans.
