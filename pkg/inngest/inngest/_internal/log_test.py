from __future__ import annotations

import unittest

from inngest._internal import log


class _FakeLogger:
    def __init__(self) -> None:
        self.info_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.set_level_calls: list[int] = []
        self.name = "fake"

    def info(self, *args: object, **kwargs: object) -> None:
        self.info_calls.append((args, kwargs))

    def setLevel(self, level: int) -> None:
        self.set_level_calls.append(level)


class TestContextLogger(unittest.TestCase):
    def test_injects_context_extras(self) -> None:
        underlying = _FakeLogger()
        ctx_logger = log.ContextLogger(
            underlying,  # type: ignore[arg-type]
            {"inngest.job_id": "j1", "inngest.run_id": "r1"},
        )

        ctx_logger.info("hello")  # type: ignore[operator]

        assert len(underlying.info_calls) == 1
        args, kwargs = underlying.info_calls[0]
        assert args == ("hello",)
        assert kwargs["extra"] == {
            "inngest.job_id": "j1",
            "inngest.run_id": "r1",
        }

    def test_collisions(self) -> None:
        """
        We win collisions: users cannot clobber our metadata. This is OK since
        we namespace.
        """

        underlying = _FakeLogger()
        ctx_logger = log.ContextLogger(
            underlying,  # type: ignore[arg-type]
            {"inngest.run_id": "system"},
        )

        ctx_logger.info(  # type: ignore[operator]
            "hello", extra={"inngest.run_id": "user", "user_field": "value"}
        )

        _, kwargs = underlying.info_calls[0]
        assert kwargs["extra"] == {
            "inngest.run_id": "system",
            "user_field": "value",
        }
