"""
Sentry middleware for Inngest.

NOT STABLE! This is an experimental feature and may change in the future. If
you'd like to use it, we recommend copying this file into your source code.
"""

from __future__ import annotations

import sentry_sdk

import inngest


class SentryMiddleware(inngest.MiddlewareSync):
    """
    Middleware that adds Sentry tags and captures exceptions.
    """

    def __init__(
        self,
        client: inngest.Inngest,
        raw_request: object,
    ) -> None:
        """
        Args:
        ----
            client: Inngest client.
            raw_request: Framework/platform specific request object.
        """

        super().__init__(client, raw_request)

        if sentry_sdk.is_initialized() is False:
            client.logger.warning("Sentry SDK is not initialized")

        sentry_sdk.set_tag("inngest.app.id", client.app_id)

    def before_response(self) -> None:  # noqa: D102
        sentry_sdk.flush()

    def transform_input(  # noqa: D102
        self,
        ctx: inngest.Context,
        function: inngest.Function,
        steps: inngest.StepMemos,
    ) -> None:
        sentry_sdk.set_tag("inngest.event.count", len(ctx.events))
        sentry_sdk.set_tag("inngest.event.id", ctx.event.id)
        sentry_sdk.set_tag("inngest.event.name", ctx.event.name)
        sentry_sdk.set_tag("inngest.function.id", function.local_id)
        sentry_sdk.set_tag("inngest.function.name", function.name)
        sentry_sdk.set_tag("inngest.run.id", ctx.run_id)

    def transform_output(self, output: inngest.TransformOutputResult) -> None:  # noqa: D102
        if output.error:
            sentry_sdk.capture_exception(output.error)
