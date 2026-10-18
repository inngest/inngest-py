"""Checkpoint protocol and replay tests against the real Inngest dev server."""

import asyncio
import collections
import datetime
import json
import pathlib
import subprocess
import threading
import time
import typing
import uuid

import fastapi
import httpx
import inngest
import inngest.fast_api
import inngest_encryption
import pytest
import uvicorn
from inngest._internal import net as sdk_net
from inngest.experimental import dev_server
from test_core import base, helper, net


@pytest.mark.parametrize("sync", [True, False])
@pytest.mark.parametrize(
    "scenario",
    [
        "sequential",
        "disabled",
        "lost_ack",
        "outage",
        "wait",
        "parallel",
        "retry",
        "deadline",
        "encryption",
        "function_error",
    ],
)
def test_checkpoint_replay(sync: bool, scenario: str) -> None:
    name = f"checkpoint-{uuid.uuid4().hex}"
    executions: list[str] = []
    calls: collections.Counter[str] = collections.Counter()
    checkpoints: list[dict[str, typing.Any]] = []
    run_ids: list[str] = []
    forward = httpx.Client(timeout=5)
    failed_once = False

    def transport(req: httpx.Request) -> httpx.Response:
        nonlocal failed_once
        if "/checkpoint/" not in req.url.path:
            return forward.send(req)
        payload = json.loads(req.content)
        checkpoints.append(payload)
        if scenario == "outage":
            return httpx.Response(503)
        response = forward.send(req)
        assert response.status_code == 200, response.text
        if scenario == "lost_ack" and not failed_once:
            failed_once = True
            raise httpx.ReadTimeout("lost checkpoint acknowledgement")
        return response

    config = inngest.Checkpointing(
        max_runtime=datetime.timedelta(milliseconds=100)
        if scenario == "deadline"
        else datetime.timedelta(0),
    )
    encryption = inngest_encryption.EncryptionMiddleware.factory(
        "test-only-key"
    )
    client = inngest.Inngest(
        app_id=name,
        api_base_url=dev_server.server.origin,
        event_api_base_url=dev_server.server.origin,
        is_production=False,
        checkpointing=False if scenario == "disabled" else config,
        middleware=[encryption] if scenario == "encryption" else None,
    )
    client._http_client._http_client_sync = httpx.Client(
        transport=httpx.MockTransport(transport)
    )
    client._http_client._http_client = sdk_net.ThreadAwareAsyncHTTPClient(
        transport=httpx.MockTransport(transport)
    ).initialize()

    def callback(key: str) -> dict[str, str]:
        calls[key] += 1
        if scenario == "retry" and key in ("a", "b") and calls[key] == 1:
            raise ValueError(f"fail {key} once")
        if scenario == "deadline" and key == "a":
            time.sleep(0.15)
        return {"key": key}

    def fn_sync(ctx: inngest.ContextSync) -> object:
        executions.append(ctx.run_id)
        run_ids.append(ctx.run_id)
        a = ctx.step.run("same", callback, "a")
        if scenario in ("wait", "encryption"):
            ctx.step.sleep("pause", datetime.timedelta(seconds=1))
        if scenario == "parallel":
            ctx.group.parallel(
                (
                    lambda: ctx.step.run("p1", callback, "p1"),
                    lambda: ctx.step.run("p2", callback, "p2"),
                )
            )
        b = ctx.step.run("same", callback, "b")
        if scenario == "function_error" and len(executions) == 1:
            raise ValueError("function failed after checkpointing")
        return [a, b]

    async def fn_async(ctx: inngest.Context) -> object:
        async def cb(key: str) -> dict[str, str]:
            return callback(key)

        executions.append(ctx.run_id)
        run_ids.append(ctx.run_id)
        a = await ctx.step.run("same", cb, "a")
        if scenario in ("wait", "encryption"):
            await ctx.step.sleep("pause", datetime.timedelta(seconds=1))
        if scenario == "parallel":
            await ctx.group.parallel(
                (
                    lambda: ctx.step.run("p1", cb, "p1"),
                    lambda: ctx.step.run("p2", cb, "p2"),
                )
            )
        b = await ctx.step.run("same", cb, "b")
        if scenario == "function_error" and len(executions) == 1:
            raise ValueError("function failed after checkpointing")
        return [a, b]

    fn = client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event=name), retries=1
    )(fn_sync if sync else fn_async)
    app = fastapi.FastAPI()
    inngest.fast_api.serve(app, client, [fn])
    port = net.get_available_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base.register(port)
        client.send_sync(inngest.Event(name=name))

        async def check() -> helper._Run:
            await base.wait_for_truthy(lambda: run_ids)
            return await helper.client.wait_for_run_status(
                run_ids[0], helper.RunStatus.COMPLETED, timeout=35
            )

        run = asyncio.run(check())
        expected: object = [{"key": "a"}, {"key": "b"}]
        assert run.output is not None
        output = json.loads(run.output)
        if scenario == "encryption":
            output = encryption(client, None)._decrypt(output)
        assert output == expected
        assert calls["a"] == (2 if scenario == "retry" else 1)
        assert calls["b"] == (2 if scenario == "retry" else 1)
        if scenario in ("sequential", "lost_ack"):
            assert len(executions) == 1
            assert len(checkpoints) == (3 if scenario == "lost_ack" else 2)
        if scenario == "disabled":
            assert len(executions) == 3
            assert not checkpoints
        if scenario in (
            "outage",
            "deadline",
            "wait",
            "encryption",
            "function_error",
        ):
            assert len(executions) > 1
        if scenario == "parallel":
            assert calls["p1"] == calls["p2"] == 1
        if scenario == "encryption":
            assert all(
                step["data"]["__ENCRYPTED__"]
                for cp in checkpoints
                for step in cp["steps"]
            )
        if scenario not in ("disabled", "deadline", "retry"):
            assert checkpoints, "The test must exercise the checkpoint API"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        forward.close()


@pytest.mark.parametrize("sync", [True, False])
@pytest.mark.parametrize("crash", ["before", "after"])
def test_worker_restart(sync: bool, crash: str, tmp_path: pathlib.Path) -> None:
    name = f"checkpoint-crash-{uuid.uuid4().hex}"
    port = net.get_available_port()
    command = [
        "uv",
        "run",
        "python",
        str(pathlib.Path(__file__).with_name("checkpoint_worker.py")),
        "--name",
        name,
        "--port",
        str(port),
        "--origin",
        dev_server.server.origin,
        "--directory",
        str(tmp_path),
        "--crash",
        crash,
    ]
    if sync:
        command.append("--sync")
    with (tmp_path / "worker.log").open("w", encoding="utf-8") as logs:
        worker = subprocess.Popen(command, stdout=logs, stderr=logs)
        try:
            base.register(port)
            with httpx.Client() as http:
                response = http.post(
                    f"{dev_server.server.origin}/e/test",
                    json={"name": name, "data": {}},
                )
                response.raise_for_status()
            assert worker.wait(timeout=15) == 23
            worker = subprocess.Popen(command, stdout=logs, stderr=logs)
            base.register(port)
            run_id = (tmp_path / "run-id").read_text(encoding="utf-8")
            run = asyncio.run(
                helper.client.wait_for_run_status(
                    run_id,
                    helper.RunStatus.COMPLETED,
                    timeout=30,
                )
            )
            assert run.output is not None
            assert json.loads(run.output) == ["a", "b"]
            effects = (
                (tmp_path / "effects").read_text(encoding="utf-8").splitlines()
            )
            assert effects.count("a") == (1 if crash == "after" else 2)
            assert effects.count("b") == 1
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
