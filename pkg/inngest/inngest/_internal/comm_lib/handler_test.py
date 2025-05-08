from __future__ import annotations

import datetime
import logging
import unittest

import inngest
from inngest._internal import errors

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
