from __future__ import annotations

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """
    Grok adapter
    """

    def __init__(
        self,
        *,
        auth_key: str,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        model: str,
    ) -> None:
        """
        Args:
        ----
            auth_key: Grok API key.
            base_url: Grok API URL.
            headers: Additional headers to send with the request.
            model: Grok model to use.
        """

        self._auth_key = auth_key
        self._headers = headers or {}
        self._model = model
        self._url = base_url or "https://api.x.ai/v1"

    def auth_key(self) -> str:
        """
        Return the authentication key for the adapter.
        """

        return self._auth_key

    def format(self) -> str:
        """
        Return the format for the adapter.
        """

        return "openai-chat"

    def headers(self) -> dict[str, str]:
        """
        Return the headers for the adapter.
        """

        return self._headers

    def on_call(self, body: dict[str, object]) -> None:
        """
        Modify the request body.
        """

        if not body.get("model"):
            body["model"] = self._model

    def url_infer(self) -> str:
        """
        Return the URL for generating text.
        """

        return self._url.rstrip("/") + "/chat/completions"
