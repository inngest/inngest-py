"""
Check SDK-side rejection of missing targets and non-finite scores. Real-server
tests verify successful writes, but cannot prove invalid inputs fail locally.
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

        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(204)

        transport = httpx.MockTransport(handle)
        self.client._http_client._http_client_sync = httpx.Client(
            transport=transport
        )
        self.client._http_client._http_client = net.ThreadAwareAsyncHTTPClient(
            transport=transport
        ).initialize()

    def test_invalid_scores_fail_before_sending(self) -> None:
        """
        Report missing targets and invalid scores to the caller before sending.
        Otherwise feedback could be lost to an invalid request or attributed to
        an unintended run. Non-finite values cannot represent JSON scores.
        """

        cases: list[tuple[str, float, str | None, str]] = [
            ("missing target", 1.0, None, "provide run_id"),
            ("blank target", 1.0, " ", "run_id must"),
            ("NaN score", float("nan"), "run", "finite number"),
            ("infinite score", float("inf"), "run", "finite number"),
        ]
        for mode, is_sync in [("async", False), ("sync", True)]:
            for description, value, run_id, message in cases:
                with self.subTest(mode=mode, case=description):
                    with self.assertRaisesRegex(ValueError, message):
                        if is_sync:
                            self.client.score_sync(
                                run_id=run_id, name="quality", value=value
                            )
                        else:
                            asyncio.run(
                                self.client.score(
                                    run_id=run_id, name="quality", value=value
                                )
                            )
                    assert self.requests == []
