"""Experimental deferred functions. Register them alongside normal functions."""

from __future__ import annotations

import typing

from inngest._internal import (
    client_lib,
    execution_lib,
    function,
    middleware_lib,
    server_lib,
    types,
)
from inngest._internal.deferred import DeferHandle, DeferredParent
from inngest._internal.scores import ExperimentRef

T = typing.TypeVar("T")


class DeferredFunction(function.Function[T]):
    """A separately retried function scheduled when its parent run finishes."""

    def _prepare(
        self, ctx: execution_lib.Context | execution_lib.ContextSync
    ) -> None:
        parents: list[DeferredParent] = []
        events: list[server_lib.Event] = []
        for event in [*ctx.events, ctx.event]:
            data = dict(event.data)
            routing = data.pop("_inngest", None)
            if not isinstance(routing, dict):
                raise ValueError("Deferred event is missing parent metadata")
            slug, run_id = (
                routing.get("parent_fn_slug"),
                routing.get("parent_run_id"),
            )
            if not isinstance(slug, str) or not isinstance(run_id, str):
                raise ValueError("Deferred event is missing parent identifiers")
            raw_ref = data.pop("_inngestExperiment", None)
            ref = None
            if isinstance(raw_ref, dict):
                name, variant = (
                    raw_ref.get("experimentName"),
                    raw_ref.get("variant"),
                )
                if isinstance(name, str) and isinstance(variant, str):
                    ref = ExperimentRef(experiment_name=name, variant=variant)
            parents.append(
                DeferredParent(fn_slug=slug, run_id=run_id, experiment=ref)
            )
            events.append(event.model_copy(update={"data": data}))
        ctx.events = events[:-1]
        ctx.event = events[-1]
        ctx.parents = parents[:-1]

    async def call(
        self,
        client: client_lib.Inngest,
        ctx: execution_lib.Context,
        fn_id: str,
        middleware: middleware_lib.MiddlewareManager,
    ) -> execution_lib.CallResult:
        """Expose parent metadata before execution middleware and the handler."""
        try:
            self._prepare(ctx)
        except Exception as err:
            return execution_lib.CallResult(err)
        return await super().call(client, ctx, fn_id, middleware)

    def call_sync(
        self,
        client: client_lib.Inngest,
        ctx: execution_lib.ContextSync,
        fn_id: str,
        middleware: middleware_lib.MiddlewareManager,
    ) -> execution_lib.CallResult:
        """Prepare parent metadata for a synchronous deferred handler."""
        try:
            self._prepare(ctx)
        except Exception as err:
            return execution_lib.CallResult(err)
        return super().call_sync(client, ctx, fn_id, middleware)


def create_defer(
    client: client_lib.Inngest,
    *,
    fn_id: str,
    name: str | None = None,
    retries: int | None = None,
    concurrency: list[server_lib.Concurrency] | None = None,
    cancel: list[server_lib.Cancel] | None = None,
    debounce: server_lib.Debounce | None = None,
    idempotency: str | None = None,
    middleware: list[middleware_lib.UninitializedMiddleware] | None = None,
    output_type: object = types.EmptySentinel,
    priority: server_lib.Priority | None = None,
    rate_limit: server_lib.RateLimit | None = None,
    throttle: server_lib.Throttle | None = None,
    timeouts: server_lib.Timeouts | None = None,
    singleton: server_lib.Singleton | None = None,
) -> typing.Callable[
    [
        execution_lib.FunctionHandlerAsync[T]
        | execution_lib.FunctionHandlerSync[T]
    ],
    DeferredFunction[T],
]:
    """Decorate a deferred handler; its event trigger is supplied by the SDK."""
    slug = f"{client.app_id}-{fn_id}"
    if not fn_id or any(char in slug for char in "'\\\n\r"):
        raise ValueError(
            "Deferred function ID cannot contain quotes, backslashes, or newlines"
        )

    def decorate(
        handler: execution_lib.FunctionHandlerAsync[T]
        | execution_lib.FunctionHandlerSync[T],
    ) -> DeferredFunction[T]:
        regular = client.create_function(
            fn_id=fn_id,
            name=name,
            retries=retries,
            concurrency=concurrency,
            cancel=cancel,
            debounce=debounce,
            idempotency=idempotency,
            middleware=middleware,
            output_type=output_type,
            priority=priority,
            rate_limit=rate_limit,
            throttle=throttle,
            timeouts=timeouts,
            singleton=singleton,
            trigger=server_lib.TriggerEvent(
                event="inngest/deferred.schedule",
                expression=f"event.data._inngest.fn_slug == '{slug}'",
            ),
        )(handler)
        return DeferredFunction(
            regular._opts, regular._triggers, handler, output_type, middleware
        )

    return decorate


__all__ = ["DeferHandle", "DeferredFunction", "DeferredParent", "create_defer"]
