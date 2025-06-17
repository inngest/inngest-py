from __future__ import annotations

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """
    Anthropic adapter
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
            auth_key: Gemini API key.
            base_url: Gemini API URL.
            headers: Additional headers to send with the request.
            model: Gemini model to use.
        """

        self._auth_key = auth_key
        self._headers = headers or {}
        self._model = model
        self._url = (
            base_url or "https://generativelanguage.googleapis.com/v1beta/"
        )

    def auth_key(self) -> str:
        """
        Return the authentication key for the adapter.
        """

        return self._auth_key

    def format(self) -> str:
        """
        Return the format for the adapter.
        """

        return "gemini"

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

        return self._url.rstrip("/") + f":generateContent?key={self._auth_key}"
