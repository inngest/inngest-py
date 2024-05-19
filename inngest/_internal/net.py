from __future__ import annotations

import hashlib
import hmac
import http
import os
import threading
import typing
import urllib.parse

import httpx

from . import async_lib, const, errors, transforms, types


class ThreadAwareAsyncHTTPClient(httpx.AsyncClient):
    """
    Thin wrapper around httpx.AsyncClient. It keeps track of the thread it was
    created in, which is critical since asyncio is not thread safe: calling an
    async method in a different thread will raise an exception
    """

    _creation_thread_id: typing.Optional[int] = None

    def is_same_thread(self) -> bool:
        if self._creation_thread_id is None:
            raise Exception("did not initialize ThreadAwareAsyncHTTPClient")

        current_thread_id = threading.get_ident()
        return self._creation_thread_id == current_thread_id

    def initialize(self) -> ThreadAwareAsyncHTTPClient:
        self._creation_thread_id = threading.get_ident()
        return self


def create_headers(
    *,
    env: typing.Optional[str],
    framework: typing.Optional[const.Framework],
    server_kind: typing.Optional[const.ServerKind],
) -> dict[str, str]:
    """
    Create standard headers that should exist on every possible outgoing
    request.
    """

    headers = {
        const.HeaderKey.CONTENT_TYPE.value: "application/json",
        const.HeaderKey.SDK.value: f"inngest-{const.LANGUAGE}:v{const.VERSION}",
        const.HeaderKey.USER_AGENT.value: f"inngest-{const.LANGUAGE}:v{const.VERSION}",
    }

    if env is not None:
        headers[const.HeaderKey.ENV.value] = env
    if framework is not None:
        headers[const.HeaderKey.FRAMEWORK.value] = framework.value
    if server_kind is not None:
        headers[const.HeaderKey.EXPECTED_SERVER_KIND.value] = server_kind.value

    return headers


def create_serve_url(
    *,
    request_url: str,
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> str:
    """
    Create the serve URL, which is the URL that the Executor will use to reach
    the SDK.

    Args:
    ----
        request_url: The URL that the Executor is using to reach the SDK.
        serve_origin: User-specified override for the serve origin.
        serve_path: User-specified override for the serve path.
    """

    # User can also specify these via env vars. The env vars take precedence.
    serve_origin = os.getenv(const.EnvKey.SERVE_ORIGIN.value, serve_origin)
    serve_path = os.getenv(const.EnvKey.SERVE_PATH.value, serve_path)

    parsed_url = urllib.parse.urlparse(request_url)
    new_scheme = parsed_url.scheme
    new_netloc = parsed_url.netloc
    new_path = parsed_url.path

    if serve_origin is not None:
        has_scheme = "://" in serve_origin
        if has_scheme:
            parsed_origin = urllib.parse.urlparse(serve_origin)
            new_scheme = parsed_origin.scheme or new_scheme
            new_netloc = parsed_origin.netloc or new_netloc
        else:
            new_scheme = "https"
            new_netloc = serve_origin

    if serve_path is not None:
        new_path = serve_path

    return urllib.parse.urlunparse(
        (new_scheme, new_netloc, new_path, "", "", "")
    )


async def fetch_with_auth_fallback(
    client: ThreadAwareAsyncHTTPClient,
    client_sync: httpx.Client,
    request: httpx.Request,
    *,
    signing_key: typing.Optional[str],
    signing_key_fallback: typing.Optional[str],
) -> httpx.Response:
    """
    Send an HTTP request with the given signing key. If the response is a 401 or
    403, then try again with the fallback signing key
    """

    if signing_key is not None:
        request.headers[
            const.HeaderKey.AUTHORIZATION.value
        ] = f"Bearer {transforms.hash_signing_key(signing_key)}"

    res = await fetch_with_thready_safety(
        client,
        client_sync,
        request,
    )
    if (
        res.status_code
        in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)
        and signing_key_fallback is not None
    ):
        # Try again with the signing key fallback
        request.headers[
            const.HeaderKey.AUTHORIZATION.value
        ] = f"Bearer {transforms.hash_signing_key(signing_key_fallback)}"

        res = await fetch_with_thready_safety(
            client,
            client_sync,
            request,
        )

    return res


def fetch_with_auth_fallback_sync(
    client: httpx.Client,
    request: httpx.Request,
    *,
    signing_key: typing.Optional[str],
    signing_key_fallback: typing.Optional[str],
) -> httpx.Response:
    """
    Send an HTTP request with the given signing key. If the response is a 401 or
    403, then try again with the fallback signing key
    """

    if signing_key is not None:
        request.headers[
            const.HeaderKey.AUTHORIZATION.value
        ] = f"Bearer {transforms.hash_signing_key(signing_key)}"

    res = client.send(request)
    if (
        res.status_code
        in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)
        and signing_key_fallback is not None
    ):
        # Try again with the signing key fallback
        request.headers[
            const.HeaderKey.AUTHORIZATION.value
        ] = f"Bearer {transforms.hash_signing_key(signing_key_fallback)}"
        res = client.send(request)

    return res


def normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    """
    Ensure that known headers are in the correct casing.
    """

    new_headers = {}

    for k, v in headers.items():
        for header_key in const.HeaderKey:
            if k.lower() == header_key.value.lower():
                k = header_key.value

        new_headers[k] = v

    return new_headers


def parse_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme == "":
        parsed._replace(scheme="https")

    return parsed.geturl()


async def fetch_with_thready_safety(
    client: ThreadAwareAsyncHTTPClient,
    client_sync: httpx.Client,
    request: httpx.Request,
) -> httpx.Response:
    """
    Safely handles the situation where the async HTTP client is called in a
    different thread.
    """

    if client.is_same_thread() is True:
        # Python freaks out if you call httpx.AsyncClient's methods in multiple
        # threads. So we'll only use it if we're in the same thread as its first
        # method call
        return await client.send(request)

    loop = async_lib.get_event_loop()
    if loop is None:
        return client_sync.send(request)

    return await loop.run_in_executor(
        None,
        lambda: client_sync.send(request),
    )


class RequestSignature:
    _signature: typing.Optional[str] = None
    _timestamp: typing.Optional[int] = None

    def __init__(
        self,
        body: bytes,
        headers: dict[str, str],
        mode: const.ServerKind,
    ) -> None:
        self._body = body
        self._mode = mode

        sig_header = headers.get(const.HeaderKey.SIGNATURE.value)
        if sig_header is not None:
            parsed = urllib.parse.parse_qs(sig_header)
            if "t" in parsed:
                self._timestamp = int(parsed["t"][0])
            if "s" in parsed:
                self._signature = parsed["s"][0]

    def _validate(
        self,
        signing_key: typing.Optional[str],
    ) -> types.MaybeError[None]:
        if self._mode == const.ServerKind.DEV_SERVER:
            return None

        if signing_key is None:
            return errors.SigningKeyMissingError(
                "cannot validate signature in production mode without a signing key"
            )

        if self._signature is None:
            return errors.HeaderMissingError(
                f"cannot validate signature in production mode without a {const.HeaderKey.SIGNATURE.value} header"
            )

        mac = hmac.new(
            transforms.remove_signing_key_prefix(signing_key).encode("utf-8"),
            self._body,
            hashlib.sha256,
        )
        mac.update(str(self._timestamp).encode("utf-8"))
        if not hmac.compare_digest(self._signature, mac.hexdigest()):
            return errors.SigVerificationFailedError()

        return None

    def validate(
        self,
        *,
        signing_key: typing.Optional[str],
        signing_key_fallback: typing.Optional[str],
    ) -> types.MaybeError[None]:
        """
        Validate the request signature. Falls back to the fallback signing key if
        signature validation fails with the primary signing key.

        Args:
        ----
            signing_key: The primary signing key.
            signing_key_fallback: The fallback signing key.
        """

        err = self._validate(signing_key)
        if err is not None and signing_key_fallback is not None:
            # If the signature validation failed but there's a "fallback"
            # signing key, attempt to validate the signature with the fallback
            # key
            err = self._validate(signing_key_fallback)

        return err
