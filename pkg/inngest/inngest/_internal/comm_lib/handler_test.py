from __future__ import annotations

import datetime
import json
import logging
import unittest

import inngest
from inngest._internal import comm_lib, errors, server_lib

from .handler import get_function_configs

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
client = inngest.Inngest(
    api_base_url="http://foo.bar",
    app_id="test",
    is_production=False,
    logger=logger,
)


class Test_get_function_configs(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)

    def test_full_config(self) -> None:
        """
        Ensure that there isn't a validation error when creating a
        fully-specified config.
        """

        @client.create_function(
            batch_events=inngest.Batch(
                max_size=2, timeout=datetime.timedelta(minutes=1)
            ),
            cancel=[
                inngest.Cancel(
                    event="app/cancel",
                    if_exp="true",
                    timeout=datetime.timedelta(minutes=1),
                )
            ],
            fn_id="fn",
            name="Function",
            retries=1,
            throttle=inngest.Throttle(
                limit=2, period=datetime.timedelta(minutes=1)
            ),
            singleton=inngest.Singleton(key="false", mode="skip"),
            trigger=inngest.TriggerEvent(event="app/fn"),
        )
        def fn(ctx: inngest.ContextSync) -> int:
            return 1

        configs = get_function_configs("http://foo.bar", {fn.id: fn})
        assert not isinstance(configs, Exception), (
            f"Unexpected error: {configs}"
        )

    def test_no_functions(self) -> None:
        configs = get_function_configs("http://foo.bar", {})
        assert isinstance(configs, errors.FunctionConfigInvalidError)
        assert str(configs) == "no functions found"


class TestCommHandlerRequestIDs(unittest.TestCase):
    def _create_request(
        self,
        *,
        headers: dict[str, str] | None = None,
    ) -> comm_lib.CommRequest:
        body = {
            "ctx": {
                "attempt": 0,
                "disable_immediate_execution": False,
                "run_id": "run-123",
                "stack": {"stack": []},
            },
            "event": {"name": "test/event", "data": {}},
            "events": [{"name": "test/event", "data": {}}],
            "steps": {},
            "use_api": False,
        }
        return comm_lib.CommRequest(
            body=json.dumps(body).encode("utf-8"),
            headers=headers or {},
            is_connect=False,
            public_path=None,
            query_params={
                server_lib.QueryParamKey.FUNCTION_ID.value: "test-fn"
            },
            raw_request=None,
            request_url="",
            serve_origin=None,
            serve_path=None,
        )

    def test_ctx(self) -> None:
        logger = logging.getLogger(f"{__name__}.headers")
        seen: dict[str, object] = {}
        client = inngest.Inngest(
            api_base_url="http://foo.bar",
            app_id="test",
            is_production=False,
            logger=logger,
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="test/event"),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            seen["job_id"] = ctx.job_id
            seen["request_id"] = ctx.request_id

        comm_handler = comm_lib.CommHandler(
            client=client,
            enable_unauthed_sync=None,
            framework=server_lib.Framework.FAST_API,
            functions=[fn],
            streaming=None,
        )

        res = comm_handler.post_sync(
            self._create_request(
                headers={
                    server_lib.HeaderKey.JOB_ID.value: "job-from-header",
                    server_lib.HeaderKey.REQUEST_ID.value: "req-from-header",
                }
            )
        )

        assert res.status_code == 200
        assert seen == {
            "job_id": "job-from-header",
            "request_id": "req-from-header",
        }

    def test_empty_headers(self) -> None:
        """
        Empty headers become None
        """

        logger = logging.getLogger(f"{__name__}.empty")
        seen: dict[str, object] = {}
        client = inngest.Inngest(
            api_base_url="http://foo.bar",
            app_id="test",
            is_production=False,
            logger=logger,
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="test/event"),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            seen["job_id"] = ctx.job_id
            seen["request_id"] = ctx.request_id

        comm_handler = comm_lib.CommHandler(
            client=client,
            enable_unauthed_sync=None,
            framework=server_lib.Framework.FAST_API,
            functions=[fn],
            streaming=None,
        )

        res = comm_handler.post_sync(
            self._create_request(
                headers={
                    server_lib.HeaderKey.JOB_ID.value: "",
                    server_lib.HeaderKey.REQUEST_ID.value: "",
                }
            )
        )

        assert res.status_code == 200
        assert seen == {"job_id": None, "request_id": None}
