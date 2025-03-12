"""
Ensure step and function output is encrypted and decrypted correctly
"""

import datetime
import json

import boto3
import inngest
import inngest_remote_state
import inngest_remote_state.s3
import moto
import moto.server
import test_core.helper
from inngest._internal import server_lib
from test_core import net

from . import base


class _State(base.BaseState):
    event: inngest.Event
    events: list[inngest.Event]


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    aws_port = net.get_available_port()
    aws_url = f"http://localhost:{aws_port}"
    aws_access_key_id = "test"
    aws_secret_access_key = "test"
    aws_region = "us-east-1"
    s3_bucket = "inngest"

    s3_client = boto3.client(
        "s3",
        endpoint_url=aws_url,
        region_name=aws_region,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    driver = inngest_remote_state.s3.S3Driver(
        bucket=s3_bucket,
        client=s3_client,
    )

    mw = inngest_remote_state.RemoteStateMiddleware.factory(driver)

    @client.create_function(
        fn_id=fn_id,
        middleware=[mw],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> str:
        state.run_id = ctx.run_id

        def _step_1() -> str:
            return "test string"

        step_1_output = step.run("step_1", _step_1)
        assert step_1_output == "test string"

        def _step_2() -> list[inngest.JSON]:
            return [{"a": {"b": 1}}]

        step_2_output = step.run("step_2", _step_2)
        assert step_2_output == [{"a": {"b": 1}}]

        step.sleep("zzz", datetime.timedelta(seconds=1))

        step.wait_for_event(
            "wait",
            event="never",
            timeout=datetime.timedelta(seconds=1),
        )

        return "function output"

    @client.create_function(
        fn_id=fn_id,
        middleware=[mw],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> str:
        state.run_id = ctx.run_id

        def _step_1() -> str:
            return "test string"

        step_1_output = await step.run("step_1", _step_1)
        assert step_1_output == "test string"

        def _step_2() -> list[inngest.JSON]:
            return [{"a": {"b": 1}}]

        step_2_output = await step.run("step_2", _step_2)
        assert step_2_output == [{"a": {"b": 1}}]

        await step.sleep("zzz", datetime.timedelta(seconds=1))

        await step.wait_for_event(
            "wait",
            event="never",
            timeout=datetime.timedelta(seconds=1),
        )

        return "function output"

    async def run_test(self: base.TestClass) -> None:
        aws_server = moto.server.ThreadedMotoServer(port=aws_port)
        aws_server.start()

        s3_client.create_bucket(Bucket=s3_bucket)

        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        output = json.loads(
            await test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )

        assert isinstance(output, dict)
        data = output.get("data")
        assert isinstance(data, dict)

        # Ensure the step output is remotely stored.
        assert driver._marker in data

        output = json.loads(
            await test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_2",
            )
        )
        assert isinstance(output, dict)
        data = output.get("data")
        assert isinstance(data, dict)

        # Ensure the step output is remotely stored.
        assert driver._marker in data

        assert run.output is not None
        assert json.loads(run.output) == "function output"

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
