# Sandboxes

Sandboxes are isolated microVMs for running commands, such as generated code or a repository's tests. The API is experimental and can change without a major version bump. It mirrors the TypeScript SDK's `inngest.sandboxes`, `step.sandbox`, and `group.sandbox`.

## Inside a function

`ctx.group.sandbox()` creates a sandbox for the length of a `with` block and destroys it when the block ends:

```python
import datetime

import inngest

client = inngest.Inngest(app_id="ci")


@client.create_function(
    fn_id="run-tests",
    trigger=inngest.TriggerEvent(event="ci/requested"),
)
async def run_tests(ctx: inngest.Context) -> int:
    async with ctx.group.sandbox("build") as sandbox:
        await sandbox.files.upload("write-test", "/app/test.py", "assert 1 + 1 == 2")
        result = await sandbox.commands.run(
            "test",
            ["python", "/app/test.py"],
            timeout=datetime.timedelta(minutes=5),
        )
    return result.exit_code
```

Synchronous functions use `with` instead of `async with` and drop `await`.

Every operation is a step with the ID you pass, so a replay reuses the recorded result instead of calling the API again. Step `build` creates the sandbox and `build:destroy` destroys it. The defaults are a name no other run shares, `f"{run_id}-build"`, and 2 vCPUs with 2048 MiB.

The block destroys the sandbox whenever it ends, including when it raises. A retry couldn't use the destroyed sandbox, so after that, an error the function raises is final and isn't retried. A step that fails later still retries as usual. If the destroy fails for good, it is logged and doesn't change the run's result.

A run that is cancelled or times out inside the block doesn't reach the destroy, so the sandbox runs until its own runtime limit stops it.

`ctx.step.sandbox` is the low-level API. Its `create` needs a stable, job-specific name and a size, and you destroy the sandbox yourself:

```python
sandbox = await ctx.step.sandbox.create(
    "create", name=f"job-{ctx.event.data['job_id']}", vcpu=1, memory_mb=1024
)
result = await sandbox.commands.run("run", "echo hello")
await sandbox.destroy("destroy")
```

Creating the same name with the same configuration returns the existing sandbox, so a retried create is safe. If a sandbox that this create started fails to reach RUNNING, it is destroyed before the error is raised.

### Images

Sandboxes start from `inngest/base:latest` (Debian with Node, Python, Ruby, and git) unless you pass `image`. Use `image.inngest(name)` for an image Inngest maintains, or `image.custom(ref)` for one published to your workspace: `"my-image"`, `"my-image:v1"`, or `"my-image@sha256:<hex>"`. A plain reference string works too.

```python
from inngest.experimental.sandbox import image

async with ctx.group.sandbox("build", image=image.custom("my-app:v3")) as sandbox:
    ...
```

The tag is resolved once, when the sandbox is created, and `sandbox.image_digest` records the exact image. Creating the same name again returns the original image even if the tag has moved, so use a new name to pick up a new tag. A sandbox created from a snapshot uses the snapshot's image and can't set `image`. An unknown image fails with `sandbox_image_not_found`. The SDK only selects published images; upload custom images through the `/v2/builds` REST API.

A string command runs through `/bin/sh -c`; a list runs as argv without a shell. A nonzero exit code is a result, not an error. A durable command keeps at most 2 MiB of output, from the end of each stream, and reports it in `result.output.truncated`.

Durable operations include `commands.run`, `files.upload`, `processes.start/list/get`, process `signal/wait/get_output`, `wait_until_running`, `pause`, `resume`, `snapshot`, `destroy`, and snapshot `clone/wait_until_ready/delete`. `snapshot()` runs two steps, `<id>` and `<id>:wait-until-ready`, so retrying the wait never creates a second snapshot.

`files.upload` is durable in Python because Python steps don't send their inputs to Inngest: only the path and byte count are recorded. The TypeScript SDK doesn't offer it in `step.sandbox`. Downloads and live streams are only available through the direct client, since their bytes would be recorded.

## Outside a function

`client.sandboxes` (async) and `client.sandboxes_sync` call the API immediately. They don't retry, and the caller owns cleanup:

```python
async with client.sandboxes.create(name="dev-box", vcpu=1, memory_mb=1024) as sandbox:
    print((await sandbox.commands.run("uname -a")).stdout)
    data = await sandbox.files.download("/etc/os-release")

    process = await sandbox.processes.start(["python", "-m", "http.server"])
    async with process.stream_output() as chunks:
        async for chunk in chunks:
            print(chunk.data.decode(errors="replace"))
```

`create` without `async with` returns the sandbox without destroying it. The sync client's sandboxes are their own `with` context managers. When the block raises, a failed destroy is logged rather than replacing the block's error.

Calling the direct client in a function body, outside a step, runs it again on every replay. Use `ctx.step.sandbox` there.

## Errors and retries

Failed operations raise `SandboxError` with `code`, `ambiguous`, `retryable`, `request_id`, and the related IDs. Branch on those fields, not the message. Invalid input raises `SandboxValidationError` before anything is sent.

Inside a function:

- A retryable error (`compute_unavailable`, `rate_limited`, HTTP 429 or 503, or a connection that never reached the API) retries the step. A lost response, or an HTTP 502 or 504, retries operations that are safe to repeat and is `ambiguous` for the rest.
- Any other error fails the step on that attempt. The error's fields are stored with the step, so the replay raises the same `SandboxError`, with the step's `StepError` as `__cause__`. Left uncaught, it fails the function without further retries.
- `ambiguous` means the operation may have taken effect, such as an exec whose response was lost. Check its effects before repeating it. Create, destroy, pause, resume, upload, and snapshot delete are safe to repeat. A destroy or snapshot delete whose target is already gone succeeds.

## Authentication and local development

Requests use the client's signing key and branch environment, and retry with `INNGEST_SIGNING_KEY_FALLBACK` after a 401 or 403. In Dev Server mode no signing key is needed: the Dev Server forwards sandbox requests to Inngest Cloud with your `inngest login` credentials.

## Implementation notes

The package lives in `inngest/_internal/sandbox_lib`, with public names in `inngest.experimental.sandbox`. Each REST operation in `ops.py` is a generator that yields requests and sleeps, so the async and sync transports drive the same logic. Durable steps are ordinary `step.run` calls whose results match the TypeScript SDK's protocol version 1, and they attach `inngest.sandbox` trace metadata. Two core changes support them: `errors.StepFailureError` fails a step immediately and stores `data` that replays read from `StepError.data`, and `run_context.use_span` groups steps in the trace.

Unit tests run against an in-memory API in `fake_api_test.py`. The `sandbox_login_required` integration case checks the step error round trip against a real Dev Server:

```sh
uv run pytest tests/test_inngest/test_function/test_fast_api.py tests/test_inngest/test_function/test_flask.py -k sandbox_login_required -v
```

Testing against real sandboxes needs a Cloud account with sandbox access, either through `inngest login` with the Dev Server or with a signing key.
