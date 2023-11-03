from __future__ import annotations

import datetime
import logging
import unittest

import inngest
from inngest._internal import const, errors, result

from . import comm


class Test_get_function_configs(  # pylint: disable=invalid-name
    unittest.TestCase
):
    def setUp(self) -> None:
        super().setUp()
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        self.client = inngest.Inngest(app_id="test", logger=logger)

    def test_full_config(self) -> None:
        """
        Ensure that there isn't a validation error when creating a
        fully-specified config.
        """

        @inngest.create_function(
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
        def fn(**_kwargs: object) -> int:
            return 1

        handler = comm.CommHandler(
            base_url="http://foo.bar",
            client=self.client,
            framework=const.Framework.FLASK,
            functions=[fn],
        )
        assert result.is_ok(handler.get_function_configs("http://foo.bar"))

        match handler.get_function_configs("http://foo.bar"):
            case result.Ok(_):
                assert True
            case result.Err(err):
                assert False, f"Unexpected error: {err}"

    def test_no_functions(self) -> None:
        functions: list[inngest.Function] = []

        handler = comm.CommHandler(
            base_url="http://foo.bar",
            client=self.client,
            framework=const.Framework.FLASK,
            functions=functions,
        )

        match handler.get_function_configs("http://foo.bar"):
            case result.Ok(_):
                assert False, "Expected error"
            case result.Err(err):
                assert isinstance(err, errors.InvalidConfig)
                assert str(err) == "no functions found"
