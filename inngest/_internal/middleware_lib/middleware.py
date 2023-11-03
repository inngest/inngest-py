from __future__ import annotations

import typing

from inngest._internal import execution, types

# Prevent circular import
if typing.TYPE_CHECKING:
    from inngest._internal import client_lib


class Middleware:
    def __init__(self, client: client_lib.Inngest) -> None:
        self.client = client

    async def after_execution(self) -> None:
        """
        After executing new code. Called multiple times per run when using
        steps.
        """

        return None

    async def before_execution(self) -> None:
        """
        Before executing new code. Called multiple times per run when using
        steps.
        """

        return None

    async def before_response(self) -> None:
        """
        After the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps.
        """

        return None

    async def transform_input(
        self,
        call_input: execution.TransformableCallInput,
    ) -> execution.TransformableCallInput:
        """
        Before calling a function or step. Used to replace certain arguments in
        the function. Called multiple times per run when using steps.
        """

        return call_input

    async def transform_output(
        self,
        output: types.Serializable,
    ) -> types.Serializable:
        """
        After a function or step returns. Used to modify the returned data.
        Called multiple times per run when using steps. Not called when an error
        is thrown.
        """

        return output


class MiddlewareSync:
    client: client_lib.Inngest

    def __init__(self, client: client_lib.Inngest) -> None:
        self.client = client

    def after_execution(self) -> None:
        """
        After executing new code. Called multiple times per run when using
        steps.
        """

        return None

    def before_execution(self) -> None:
        """
        Before executing new code. Called multiple times per run when using
        steps.
        """

        return None

    def before_response(self) -> None:
        """
        After the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps.
        """

        return None

    def transform_input(
        self,
        call_input: execution.TransformableCallInput,
    ) -> execution.TransformableCallInput:
        """
        Before calling a function or step. Used to replace certain arguments in
        the function. Called multiple times per run when using steps.
        """

        return call_input

    def transform_output(
        self,
        output: types.Serializable,
    ) -> types.Serializable:
        """
        After a function or step returns. Used to modify the returned data.
        Called multiple times per run when using steps. Not called when an error
        is thrown.
        """

        return output
