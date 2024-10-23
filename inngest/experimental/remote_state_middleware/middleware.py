from __future__ import annotations

import typing

import inngest


class StateDriver(typing.Protocol):
    """
    Protocol for the state driver.
    """

    def load_steps(self, steps: inngest.StepMemos) -> None:
        """
        Retrieve the value associated with the key.

        Args:
        ----
            steps: Steps whose output may need to be loaded from the remote store.
        """

        ...

    def save_step(
        self,
        value: object,
    ) -> dict[str, object]:
        """
        Store the value and return a key to retrieve it later.

        Args:
        ----
            value: Output for an ended step.
        """

        ...


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

        self._driver.load_steps(steps)

    def transform_output(self, result: inngest.TransformOutputResult) -> None:
        """
        Store step output externally and replace with a marker and key.
        """

        if result.step is None:
            return None

        if result.has_output() is False:
            return None

        result.output = self._driver.save_step(result.output)
