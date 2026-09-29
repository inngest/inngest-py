"""
Check local validation and failures reaching callers. Real-server tests cover
successful writes; these tests cover cases where a score cannot be saved.
"""

from __future__ import annotations

import asyncio
import unittest

import httpx

import inngest

from . import net


class TestScores(unittest.TestCase):
    def setUp(self) -> None:
        self.client = inngest.Inngest(
            app_id="scores",
            is_production=False,
            api_base_url="http://scores.test",
        )
        self.requests: list[httpx.Request] = []
        self.response = httpx.Response(204)
        self.transport_error: httpx.TransportError | None = None

        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if self.transport_error is not None:
                raise self.transport_error
            return self.response

        transport = httpx.MockTransport(handle)
        self.client._http_client._http_client_sync = httpx.Client(
            transport=transport
        )
        self.client._http_client._http_client = net.ThreadAwareAsyncHTTPClient(
            transport=transport
        ).initialize()

    def test_invalid_scores_fail_before_sending(self) -> None:
        """
        Reject invalid targets, names, and values locally so callers can correct
        feedback that the backend cannot store.
        """

        cases: list[tuple[str, str, float, str, str | None, str]] = [
            ("blank run", "quality", 1, " ", None, "run_id must"),
            ("empty step", "quality", 1, "run", "", "step_id must"),
            ("blank step", "quality", 1, "run", " ", "step_id must"),
            ("empty name", "", 1, "run", None, "non-empty string"),
            ("blank name", " ", 1, "run", None, "non-empty string"),
            ("quoted name", "user's", 1, "run", None, "single quotes"),
            ("control character", "a\nb", 1, "run", None, "control characters"),
            ("DEL character", "a\x7fb", 1, "run", None, "control characters"),
            ("UTF-8 byte limit", "é" * 65, 1, "run", None, "128 UTF-8 bytes"),
            (
                "NaN score",
                "quality",
                float("nan"),
                "run",
                None,
                "finite number",
            ),
            (
                "infinite score",
                "quality",
                float("inf"),
                "run",
                None,
                "finite number",
            ),
        ]
        for mode, is_sync in [("async", False), ("sync", True)]:
            for description, name, value, run_id, step_id, message in cases:
                with self.subTest(mode=mode, case=description):
                    with self.assertRaisesRegex(ValueError, message):
                        if is_sync:
                            self.client.score_sync(
                                run_id=run_id,
                                step_id=step_id,
                                name=name,
                                value=value,
                            )
                        else:
                            asyncio.run(
                                self.client.score(
                                    run_id=run_id,
                                    step_id=step_id,
                                    name=name,
                                    value=value,
                                )
                            )
                    assert self.requests == []

    def test_failed_writes_raise_to_the_caller(self) -> None:
        """Callers must be able to detect unsaved feedback and retry or report it."""
        cases: list[tuple[str, int, httpx.TransportError | None, str]] = [
            ("authentication rejected", 401, None, "401"),
            ("server failure", 500, None, "500"),
            (
                "connection failure",
                204,
                httpx.ConnectError("offline"),
                "offline",
            ),
        ]
        for mode, is_sync in [("async", False), ("sync", True)]:
            for description, status, error, message in cases:
                with self.subTest(mode=mode, case=description):
                    self.requests.clear()
                    self.response = httpx.Response(status)
                    self.transport_error = error
                    with self.assertRaisesRegex(Exception, message):
                        if is_sync:
                            self.client.score_sync(
                                run_id="run", name="quality", value=1
                            )
                        else:
                            asyncio.run(
                                self.client.score(
                                    run_id="run", name="quality", value=1
                                )
                            )
                    assert self.requests
