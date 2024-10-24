"""
Ensure step and function output is encrypted and decrypted correctly
"""

import json

import boto3
import moto
import moto.server

import inngest
import tests.helper
from inngest._internal import server_lib
from inngest.experimental import remote_state_middleware
from tests import net

from . import base


class _State(base.BaseState):
    event: inngest.Event
    events: list[inngest.Event]


@moto.mock_aws
def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    aws_server = moto.server.ThreadedMotoServer(port=net.get_available_port())
    aws_server.start()
    aws_host, aws_port = aws_server.get_host_and_port()

    conn = boto3.resource("s3", region_name="us-east-1")
    conn.create_bucket(Bucket="inngest")
    driver = remote_state_middleware.S3Driver(
        bucket="inngest",
        endpoint_url=f"http://{aws_host}:{aws_port}",
        region_name="us-east-1",
    )

    driver.save_step("run_id", "value")

    @client.create_function(
        fn_id=fn_id,
        middleware=[
            remote_state_middleware.RemoteStateMiddleware.factory(driver)
        ],
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

        return "function output"

    @client.create_function(
        fn_id=fn_id,
        middleware=[
            remote_state_middleware.RemoteStateMiddleware.factory(driver)
        ],
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

        return "function output"

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = state.wait_for_run_id()
        run = tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        # Ensure that step_1 output is encrypted and its value is correct
        output = json.loads(
            tests.helper.client.get_step_output(
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
            tests.helper.client.get_step_output(
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
