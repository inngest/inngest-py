import asyncio
import json
import signal
import subprocess
import time
import typing

import httpx
import inngest
import pytest
import test_core

from .base import BaseTest


class TestSignals(BaseTest):
    @pytest.mark.timeout(30, method="thread")
    async def test_sigterm(self) -> None:
        """
        Test that the worker waits for an execution request to complete when
        receiving a SIGTERM.
        """

        app_id = test_core.random_suffix("app")
        event_name = test_core.random_suffix("event")
        proc = _start_app(app_id, event_name)
        self.addCleanup(proc.terminate)

        # Wait for app to be ready for execution.
        await _wait_for_app(app_id, True)

        # Trigger the function.
        client = inngest.Inngest(app_id="test", is_production=False)
        event_ids = await client.send(inngest.Event(name=event_name))
        assert len(event_ids) == 1

        # Wait for the run to queue.
        run_ids = await test_core.helper.client.get_run_ids_from_event_id(
            event_ids[0],
            run_count=1,
        )
        assert len(run_ids) == 1
        run_id = run_ids[0]

        # Send signal to the worker.
        proc.send_signal(signal.SIGTERM)

        # Run still completed.
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "Hello"

        # Wait for app to close.
        await _wait_for_app(app_id, False)

        # Wait for the worker process to exit.
        proc.wait(timeout=5)
        assert proc.returncode == 0

    @pytest.mark.timeout(30, method="thread")
    async def test_non_standard_signal(self) -> None:
        """
        Test that the worker waits for an execution request to complete when
        receiving a SIGTERM.
        """

        app_id = test_core.random_suffix("app")
        event_name = test_core.random_suffix("event")
        proc = _start_app(app_id, event_name, [signal.SIGUSR1])
        self.addCleanup(proc.terminate)

        # Wait for app to be ready for execution.
        await _wait_for_app(app_id, True)

        # Trigger the function.
        client = inngest.Inngest(app_id="test", is_production=False)
        event_ids = await client.send(inngest.Event(name=event_name))
        assert len(event_ids) == 1

        # Wait for the run to queue.
        run_ids = await test_core.helper.client.get_run_ids_from_event_id(
            event_ids[0],
            run_count=1,
        )
        assert len(run_ids) == 1
        run_id = run_ids[0]

        # Send signal to the worker.
        proc.send_signal(signal.SIGUSR1)

        # Run still completed.
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == "Hello"

        # Wait for app to close.
        await _wait_for_app(app_id, False)

        # Wait for the worker process to exit.
        proc.wait(timeout=5)
        assert proc.returncode == 0


def _start_app(
    app_id: str,
    event_name: str,
    signals: typing.Optional[list[signal.Signals]] = None,
) -> subprocess.Popen[bytes]:
    signals_str = "None"
    if signals is not None:
        signals_str = "["
        signals_str += ", ".join(
            [f"signal.{sig.name}" for sig in signals],
        )
        signals_str += "]"

    # It'd be nice to avoid source code as a string, but we need a way to
    # create a completely new Python process. There doesn't seem to be
    # another way to test kill signals.
    app_code = f"""
import asyncio
import inngest
from inngest.experimental.connect import connect
import signal

client = inngest.Inngest(
    app_id="{app_id}",
    is_production=False,
)

@client.create_function(
    fn_id="fn",
    retries=0,
    trigger=inngest.TriggerEvent(event="{event_name}"),
)
async def fn(ctx: inngest.Context, step: inngest.Step) -> str:
    await asyncio.sleep(5)
    return "Hello"

asyncio.run(
    connect(
        [(client, [fn])],
        instance_id="{app_id}",
        shutdown_signals={signals_str},
    ).start()
)
    """

    return subprocess.Popen(["python", "-c", app_code])


async def _wait_for_app(app_id: str, should_exist: bool) -> None:
    async with httpx.AsyncClient() as client:
        start = time.time()
        while True:
            if time.time() - start > 10:
                raise Exception("timed out waiting for app")

            res = await client.get(
                "http://0.0.0.0:8288/v0/connect/envs/00000000-0000-4000-b000-000000000000/conns"
            )
            if res.status_code != 200:
                raise Exception(f"unexpected status code: {res.status_code}")

            body = res.json()
            if not isinstance(body, dict):
                raise Exception("unexpected response")
            data = body["data"]
            if not isinstance(data, list):
                raise Exception("unexpected response")

            exists = False
            for app in data:
                if not isinstance(app, dict):
                    raise Exception("unexpected response")

                exists = app["instance_id"] == app_id
            if exists == should_exist:
                return

            await asyncio.sleep(0.1)
