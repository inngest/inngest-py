from __future__ import annotations

import datetime
import logging
import unittest

import pytest

import inngest

from . import comm, errors


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

        @inngest.create_function_sync(
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

        handler = comm.CommHandlerSync(
            api_origin="http://foo.bar",
            client=self.client,
            framework="test",
            functions=[fn],
            logger=self.client.logger,
        )
        handler.get_function_configs("http://foo.bar")

    def test_no_functions(self) -> None:
        handler = comm.CommHandlerSync(
            api_origin="http://foo.bar",
            client=self.client,
            framework="test",
            functions=[],
            logger=self.client.logger,
        )

        with pytest.raises(errors.InvalidConfig, match="no functions found"):
            handler.get_function_configs("http://foo.bar")
