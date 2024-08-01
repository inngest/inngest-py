from __future__ import annotations

import datetime
import http
import logging
import unittest

import inngest
from inngest._internal import errors, net, server_lib

from .handler import CommHandler
from .models import CommRequest

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

dev_client = inngest.Inngest(
    api_base_url="http://foo.bar",
    app_id="test",
    is_production=False,
    logger=logger,
)

prod_client = inngest.Inngest(
    api_base_url="http://foo.bar",
    app_id="test",
    logger=logger,
    signing_key="signkey-prod-000000",
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

        @dev_client.create_function(
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
                count=2, period=datetime.timedelta(minutes=1)
            ),
            trigger=inngest.TriggerEvent(event="app/fn"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> int:
            return 1

        handler = CommHandler(
            client=dev_client,
            framework=server_lib.Framework.FLASK,
            functions=[fn],
        )

        configs = handler.get_function_configs("http://foo.bar")
        assert not isinstance(
            configs, Exception
        ), f"Unexpected error: {configs}"

    def test_no_functions(self) -> None:
        functions: list[inngest.Function] = []

        handler = CommHandler(
            client=dev_client,
            framework=server_lib.Framework.FLASK,
            functions=functions,
        )

        configs = handler.get_function_configs("http://foo.bar")
        assert isinstance(configs, errors.FunctionConfigInvalidError)
        assert str(configs) == "no functions found"


class TestSignatureVerification(unittest.IsolatedAsyncioTestCase):
    async def test_post_without_signature(self) -> None:
        # Ensure that a request without a signature is rejected. Ideally we'd
        # test this during execution, but the Dev Server doesn't support signing
        # keys yet

        functions: list[inngest.Function] = []

        handler = CommHandler(
            client=prod_client,
            framework=server_lib.Framework.FLASK,
            functions=functions,
        )

        # Create a request that mimics an execution request, but without a
        # signature
        req = CommRequest(
            body=b"{}",
            headers={},
            query_params={
                "fnId": "fn",
                "stepId": "step",
            },
            raw_request=None,
            request_url="http://foo.local",
            serve_origin=None,
            serve_path=None,
        )

        # Test both POST handlers
        for res in [await handler.post(req), handler.post_sync(req)]:
            assert res.status_code == http.HTTPStatus.INTERNAL_SERVER_ERROR
            assert isinstance(res.body, dict)
            assert res.body["code"] == "header_missing"

    async def test_post_wrong_signing_key(self) -> None:
        # Ensure that a request with an invalid signature is rejected. Ideally
        # we'd test this during execution, but the Dev Server doesn't support
        # signing keys yet

        functions: list[inngest.Function] = []

        handler = CommHandler(
            client=prod_client,
            framework=server_lib.Framework.FLASK,
            functions=functions,
        )

        body = b"{}"
        wrong_signing_key = "signkey-prod-111111"

        # Create a request that mimics an execution request, but with an invalid
        # signature
        req = CommRequest(
            body=body,
            headers={
                server_lib.HeaderKey.SIGNATURE.value: net.sign(
                    body,
                    wrong_signing_key,
                ),
            },
            query_params={
                "fnId": "fn",
                "stepId": "step",
            },
            raw_request=None,
            request_url="http://foo.local",
            serve_origin=None,
            serve_path=None,
        )

        # Test both POST handlers
        for res in [await handler.post(req), handler.post_sync(req)]:
            assert res.status_code == http.HTTPStatus.INTERNAL_SERVER_ERROR
            assert isinstance(res.body, dict)
            assert res.body["code"] == "sig_verification_failed"
