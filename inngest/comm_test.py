from __future__ import annotations

import logging
from unittest import TestCase

import pytest

import inngest

from .comm import CommHandler
from .errors import InvalidFunctionConfig


class Test_get_function_configs(TestCase):  # pylint: disable=invalid-name
    def setUp(self) -> None:
        super().setUp()
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        self.client = inngest.Inngest(id="test", logger=logger)

    def test_full_config(self) -> None:
        """
        Ensure that there isn't a validation error when creating a
        fully-specified config.
        """

        @inngest.create_function(
            inngest.FunctionOpts(
                batch_events=inngest.BatchConfig(max_size=2, timeout="1m"),
                cancel=inngest.CancelConfig(
                    event="app/cancel",
                    if_expression="true",
                    timeout="1m",
                ),
                id="fn",
                name="Function",
                retries=1,
                throttle=inngest.ThrottleConfig(count=2, period="1m"),
            ),
            inngest.TriggerEvent(event="app/fn"),
        )
        def fn(**_kwargs: object) -> int:
            return 1

        comm = CommHandler(
            api_origin="http://foo.bar",
            client=self.client,
            framework="test",
            functions=[fn],
            logger=self.client.logger,
        )
        comm.get_function_configs("http://foo.bar")

    def test_no_functions(self) -> None:
        comm = CommHandler(
            api_origin="http://foo.bar",
            client=self.client,
            framework="test",
            functions=[],
            logger=self.client.logger,
        )

        with pytest.raises(InvalidFunctionConfig, match="no functions found"):
            comm.get_function_configs("http://foo.bar")
