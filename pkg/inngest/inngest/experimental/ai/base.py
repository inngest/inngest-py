import typing


class BaseAdapter(typing.Protocol):
    """
    Base AI adapter.
    """

    def auth_key(self) -> str:
        """
        Return the authentication key for the adapter.
        """
        ...

    def format(self) -> str:
        """
        Return the format for the adapter.
        """
        ...

    def headers(self) -> dict[str, str]:
        """
        Return the headers for the adapter.
        """
        ...

    def on_call(self, body: dict[str, object]) -> None:
        """
        Modify the request body.
        """
        ...

    def url_infer(self) -> str:
        """
        Return the URL for generating text.
        """
        ...
