"""
Remote state middleware for Inngest.

NOT STABLE! This is an experimental feature and may change in the future. If
you'd like to use it, we recommend copying this file into your source code.
"""

from __future__ import annotations

import typing

import inngest


class StateDriver(typing.Protocol):
    """
    Protocol for the state driver.
    """

    def read(self, key: str) -> object:
        """
        Retrieve the value associated with the key.

        Args:
        ----
            key: Key returned from `create`.
        """

        ...

    def write(self, value: object) -> str:
        """
        Store the value and return a key to retrieve it later.

        Args:
        ----
            value: Value to store.
        """

        ...


# Marker to indicate that the data is stored remotely.
_marker: typing.Final = "__REMOTE_STATE__"


class RemoteStateMiddleware(inngest.MiddlewareSync):
    """
    Middleware that reads/writes step output in a custom store (e.g. AWS S3).
    This can drastically reduce bandwidth to/from the Inngest server, since step
    output is stored within your infrastructure rather than Inngest's.
    """

    def __init__(
        self,
        client: inngest.Inngest,
        raw_request: object,
        driver: StateDriver,
    ) -> None:
        """
        Args:
        ----
            client: Inngest client.
            raw_request: Framework/platform specific request object.
            driver: State driver.
        """

        super().__init__(client, raw_request)

        self._driver = driver

    @classmethod
    def factory(
        cls,
        driver: StateDriver,
    ) -> typing.Callable[[inngest.Inngest, object], RemoteStateMiddleware]:
        """
        Create a remote state middleware that can be passed to an Inngest client
        or function.

        Args:
        ----
            driver: State driver.
        """

        def _factory(
            client: inngest.Inngest,
            raw_request: object,
        ) -> RemoteStateMiddleware:
            return cls(
                client,
                raw_request,
                driver,
            )

        return _factory

    def transform_input(
        self,
        ctx: inngest.Context,
        function: inngest.Function,
        steps: inngest.StepMemos,
    ) -> None:
        """
        Inject remote state.
        """

        for step in steps.values():
            if not _is_external(step.data):
                continue

            if not isinstance(step.data, dict):
                continue

            key = step.data.get("key")
            if key is None:
                continue

            step.data = self._driver.read(key)

    def transform_output(self, result: inngest.TransformOutputResult) -> None:
        """
        Store step output externally and replace with a marker and key.
        """

        if result.has_output() and result.step is not None:
            result.output = {
                _marker: True,
                "key": self._driver.write(result.output),
            }


def _is_external(value: object) -> bool:
    if not isinstance(value, dict):
        return False

    if value.get(_marker) is not True:
        return False

    return True
