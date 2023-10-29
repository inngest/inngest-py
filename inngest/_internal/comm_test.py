from __future__ import annotations

import logging
from datetime import timedelta
from unittest import TestCase

import pytest

import inngest

from . import comm, errors


class Test_get_function_configs(TestCase):  # pylint: disable=invalid-name
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
            inngest.FunctionOpts(
                batch_events=inngest.BatchConfig(
                    max_size=2, timeout=timedelta(minutes=1)
                ),
                cancel=inngest.CancelConfig(
                    event="app/cancel",
                    if_exp="true",
                    timeout=timedelta(minutes=1),
                ),
                id="fn",
                name="Function",
                retries=1,
                throttle=inngest.ThrottleConfig(
                    count=2, period=timedelta(minutes=1)
                ),
            ),
            inngest.TriggerEvent(event="app/fn"),
        )
        def fn(**_kwargs: object) -> int:
            return 1

        handler = comm.CommHandler(
            api_origin="http://foo.bar",
            client=self.client,
            framework="test",
            functions=[fn],
            logger=self.client.logger,
        )
        handler.get_function_configs("http://foo.bar")

    def test_no_functions(self) -> None:
        handler = comm.CommHandler(
            api_origin="http://foo.bar",
            client=self.client,
            framework="test",
            functions=[],
            logger=self.client.logger,
        )

        with pytest.raises(errors.InvalidConfig, match="no functions found"):
            handler.get_function_configs("http://foo.bar")
