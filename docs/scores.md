# Scores

Scoring APIs are experimental.

Attach an outcome to a run, including a completed run:

```python
await client.score(run_id=original_run_id, name="approved", value=True)
```

Use `client.score_sync(...)` from synchronous code. Persist the original run ID
with the application record; `run_id` is required even inside a function. Pass
the step's user-facing ID to score that step:

```python
await client.score(
    run_id=original_run_id, step_id="answer", name="quality", value=0.75
)
```

Scores use the authenticated metadata API and merge by name; send absolute values rather than increments. HTTP/auth/transport failures are raised. Values must be finite numbers or booleans. Names must be nonblank, at most 128 UTF-8 bytes, and contain no control characters or single quotes.

The `score_completed_run` integration case verifies stored run and step scores
against Dev Server, including updating an existing score without erasing others.
Run it through async, sync, and Connect serving:

```sh
uv run pytest tests/test_inngest/test_function/test_fast_api.py tests/test_inngest/test_function/test_flask.py tests/test_inngest/test_function/test_connect.py -k score_completed_run -v
```
