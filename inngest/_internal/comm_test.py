from __future__ import annotations

import datetime
import logging
import unittest

import inngest
from inngest._internal import const, errors

from . import comm


class Test_get_function_configs(unittest.TestCase):
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
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> int:
            return 1

        handler = comm.CommHandler(
            api_base_url="http://foo.bar",
            client=self.client,
            framework=const.Framework.FLASK,
            functions=[fn],
        )

        configs = handler.get_function_configs("http://foo.bar")
        assert not isinstance(
            configs, Exception
        ), f"Unexpected error: {configs}"

    def test_no_functions(self) -> None:
        functions: list[inngest.Function] = []

        handler = comm.CommHandler(
            api_base_url="http://foo.bar",
            client=self.client,
            framework=const.Framework.FLASK,
            functions=functions,
        )

        configs = handler.get_function_configs("http://foo.bar")
        assert isinstance(configs, errors.InvalidConfigError)
        assert str(configs) == "no functions found"
