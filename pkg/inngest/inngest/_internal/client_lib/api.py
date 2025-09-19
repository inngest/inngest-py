from urllib.parse import urljoin

import httpx

from inngest._internal import net, types


class ApiClient:
    def __init__(
        self,
        http_client: net.ThreadAwareAsyncHTTPClient,
        http_client_sync: httpx.Client,
        signing_key: str | None,
        signing_key_fallback: str | None,
        env: str | None,
        api_origin: str,
    ):
        self._api_origin = api_origin
        self._http_client = http_client
        self._http_client_sync = http_client_sync
        self._signing_key = signing_key
        self._signing_key_fallback = signing_key_fallback
        self._env = env

    # TODO - Move build request as a method here
    # TODO - Move refactor post to just take a pathname and body, not a full url
    async def post(
        self, url: str, body: object
    ) -> types.MaybeError[httpx.Response]:
        """
        Perform an asynchronous HTTP POST request. Handles authn

        Args:
        ----
            url: The pathname to the endpoint, including query string
            body: The body of the request

        Returns:
        -------
            A httpx.Response object
        """
        req = self._http_client.build_request(
            "POST",
            urljoin(self._api_origin, url),
            headers=net.create_headers(
                env=self._env,
                framework=None,
                server_kind=None,
            ),
            json=body,
            timeout=self._http_client.timeout,
        )

        res = await net.fetch_with_auth_fallback(
            self._http_client,
            self._http_client_sync,
            req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        if res.status_code >= 400:
            return Exception(f"HTTP error: {res.status_code} {res.text}")

        return res

    async def get(self, url: str):
        pass
