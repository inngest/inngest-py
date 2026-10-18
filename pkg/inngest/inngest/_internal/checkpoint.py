from __future__ import annotations

import asyncio
import datetime
import random
import time
import typing
import urllib.parse

import httpx
import pydantic

from inngest._internal import net, transforms, types

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, server_lib


class Checkpointing(types.BaseModel):
    """
    Opt-in sequential checkpointing for HTTP executor requests.

    max_runtime is a cooperative invocation budget, checked between steps.
    It cannot interrupt a running Python callback. Zero means unlimited.
    Results are persisted individually, before the next step starts.
    """

    model_config = pydantic.ConfigDict(strict=True, frozen=True, extra="forbid")
    max_runtime: datetime.timedelta = pydantic.Field(
        default=datetime.timedelta(0), ge=datetime.timedelta(0)
    )


class Checkpointer:
    """Invocation-local transport; no background tasks or retained step history."""

    def __init__(
        self,
        client: client_lib.Inngest,
        request: server_lib.ServerRequest,
        config: Checkpointing,
    ) -> None:
        self._client = client
        self._request = request
        self._key = client._signing_key
        self._fallback_key = client._signing_key_fallback
        self._started = time.monotonic()
        self._budget = config.max_runtime.total_seconds()
        self._url = urllib.parse.urljoin(
            client.api_origin,
            f"/v1/checkpoint/{urllib.parse.quote(request.ctx.run_id, safe='')}/async",
        )

    @property
    def expired(self) -> bool:
        return self._budget > 0 and self.remaining <= 0

    @property
    def remaining(self) -> float:
        if self._budget == 0:
            return float("inf")
        return max(0.0, self._budget - (time.monotonic() - self._started))

    def _build_request(self, step: dict[str, object]) -> httpx.Request:
        return self._client._http_client.build_httpx_request(
            "POST",
            self._url,
            headers=net.create_headers(
                env=self._client.env, framework=None, server_kind=None
            ),
            json={
                "run_id": self._request.ctx.run_id,
                "fn_id": self._request.ctx.fn_id,
                "qi_id": self._request.ctx.qi_id,
                "steps": [step],
            },
            timeout=min(self._client._httpx_timeout, self.remaining),
        )

    def _accepted(
        self, req: httpx.Request, res: httpx.Response | Exception
    ) -> bool:
        if isinstance(res, Exception) or res.status_code != 200:
            return False
        if self._fallback_key is not None and req.headers.get(
            "authorization"
        ) == (f"Bearer {transforms.hash_signing_key(self._fallback_key)}"):
            self._key = self._fallback_key
            self._fallback_key = None
        return True

    def _retry_delay(
        self, res: httpx.Response | Exception, attempt: int
    ) -> float | None:
        if attempt >= 2:
            return None
        if isinstance(res, Exception):
            # The shared HTTP helper wraps transport exceptions.
            if not isinstance(res, httpx.TransportError) and not isinstance(
                res.__cause__, httpx.TransportError
            ):
                return None
        elif res.status_code != 429 and res.status_code < 500:
            return None
        delay: float = 0.1 * (2.0**attempt) * random.uniform(0.5, 1.5)  # noqa: S311 — retry jitter
        if not isinstance(res, Exception) and res.status_code == 429:
            try:
                delay = max(delay, float(res.headers.get("retry-after", "0")))
            except ValueError:
                return None
        # A long throttle is better handled by ordinary orchestration.
        if delay > 1 or delay >= self.remaining:
            return None
        return delay

    async def persist(self, step: dict[str, object]) -> bool:
        started = time.monotonic()
        for attempt in range(3):
            if self.expired:
                break
            req = self._build_request(step)
            res = await net.fetch_with_auth_fallback(
                self._client._http_client._http_client,
                self._client._http_client._http_client_sync,
                req,
                signing_key=self._key,
                signing_key_fallback=self._fallback_key,
            )
            if self._accepted(req, res):
                self._log_result(True, started)
                return True
            delay = self._retry_delay(res, attempt)
            if delay is None:
                break
            await asyncio.sleep(delay)
        self._log_result(False, started)
        return False

    def persist_sync(self, step: dict[str, object]) -> bool:
        started = time.monotonic()
        for attempt in range(3):
            if self.expired:
                break
            req = self._build_request(step)
            res = net.fetch_with_auth_fallback_sync(
                self._client._http_client._http_client_sync,
                req,
                signing_key=self._key,
                signing_key_fallback=self._fallback_key,
            )
            if self._accepted(req, res):
                self._log_result(True, started)
                return True
            delay = self._retry_delay(res, attempt)
            if delay is None:
                break
            time.sleep(delay)
        self._log_result(False, started)
        return False

    def _log_result(self, accepted: bool, started: float) -> None:
        log = (
            self._client.logger.info
            if accepted
            else self._client.logger.warning
        )
        log(
            "Inngest checkpoint acknowledged"
            if accepted
            else "Checkpoint unavailable; yielding to the executor",
            extra={
                "inngest_run_id": self._request.ctx.run_id,
                "checkpoint_status": "acknowledged" if accepted else "fallback",
                "checkpoint_duration_ms": (time.monotonic() - started) * 1000,
            },
        )
