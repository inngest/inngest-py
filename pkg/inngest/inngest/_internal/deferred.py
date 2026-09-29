"""
Buffer defer operations until the parent's next execution response.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import typing

from inngest._internal import errors, run_context, sessions, transforms

if typing.TYPE_CHECKING:
    from inngest._internal import execution_lib
    from inngest._internal.scores import ExperimentRef


@dataclasses.dataclass(frozen=True)
class DeferredParent:
    """The run that scheduled this deferred function."""

    fn_slug: str
    run_id: str
    experiment: ExperimentRef | None = None


class DeferHandle:
    """Cancel a scheduled defer while the server still allows cancellation."""

    def __init__(self, abort: typing.Callable[[], None]) -> None:
        self._abort = abort

    def abort(self) -> None:
        self._abort()


def _log(
    ctx: execution_lib.Context | execution_lib.ContextSync, err: Exception
) -> None:
    # Even a custom logger must not turn a rejected defer into a parent failure.
    with contextlib.suppress(Exception):
        ctx.logger.error(f"defer skipped: {err}")


def add(
    ctx: execution_lib.Context | execution_lib.ContextSync,
    defer_id: object,
    *,
    function: object,
    data: object,
    meta: sessions.EventMeta | None,
    experiment: ExperimentRef | None,
) -> DeferHandle:
    from inngest._internal import server_lib, step_lib
    from inngest._internal.step_lib.base import StepUserlandInfo
    from inngest.experimental.deferred import DeferredFunction

    try:
        run = run_context.current_run.get()
        if run is None or run.ctx is not ctx:
            raise ValueError("defer requires an active function execution")
        if not isinstance(function, DeferredFunction):
            raise ValueError("function must be created with create_defer")
        if not isinstance(defer_id, str) or not defer_id:
            raise ValueError("defer ID must be a non-empty string")
        hashed_id = transforms.hash_step_id(defer_id)
        if hashed_id in ctx._defer_seen:
            raise ValueError(f"duplicate defer ID: {defer_id}")
        prior = ctx.step._execution._request.defers
        if hashed_id not in prior:
            if not isinstance(data, dict) or not all(
                isinstance(key, str) for key in data
            ):
                raise ValueError(
                    "defer data must be an object with string keys"
                )
            if "_inngest" in data or "_inngestExperiment" in data:
                raise ValueError("defer data contains reserved routing keys")
            payload = dict(data)
            if experiment is not None:
                from inngest._internal.scores import ExperimentRef

                ref = ExperimentRef.model_validate(experiment)
                payload["_inngestExperiment"] = {
                    "experimentName": ref.experiment_name,
                    "variant": ref.variant,
                }
            opts: dict[str, object] = {"fn_slug": function.id, "input": payload}
            stamped = sessions.stamp_meta(meta, inherited_sessions=ctx.sessions)
            if stamped is not None:
                opts["meta"] = stamped
            # Snapshot and reject unserializable inputs here, before they can
            # break serialization of the parent's eventual response.
            opts = json.loads(json.dumps(opts, allow_nan=False))
            ctx._defer_ops[hashed_id] = step_lib.StepInfo(
                id=hashed_id,
                display_name=defer_id,
                name=defer_id,
                op=server_lib.Opcode.DEFER_ADD,
                opts=opts,
                userland=StepUserlandInfo(id=defer_id, index=None),
            )
        ctx._defer_seen.add(hashed_id)
        valid_id = defer_id
        target_slug = function.id

        def abort() -> None:
            try:
                active = run_context.current_run.get()
                if active is None or active.ctx is not ctx:
                    raise ValueError("abort requires the parent execution")
                if hashed_id in prior and not prior[hashed_id].abortable:
                    return
                abort_id = transforms.hash_step_id(f"{hashed_id}:abort")
                if abort_id in ctx._defer_seen:
                    return
                if ctx._defer_ops.pop(hashed_id, None) is not None:
                    # Nothing reached the server yet. Cancel locally instead
                    # of repeatedly emitting an abort on each parent replay.
                    ctx._defer_seen.add(abort_id)
                    return
                ctx._defer_ops[abort_id] = step_lib.StepInfo(
                    id=abort_id,
                    display_name=valid_id,
                    name=valid_id,
                    op=server_lib.Opcode.DEFER_ABORT,
                    opts={
                        "target_hashed_id": hashed_id,
                        "fn_slug": target_slug,
                        "id": valid_id,
                    },
                    userland=StepUserlandInfo(id=valid_id, index=None),
                )
                ctx._defer_seen.add(abort_id)
            except Exception as err:
                _log(ctx, err)

        return DeferHandle(abort)
    except Exception as err:
        _log(ctx, err)
        return DeferHandle(lambda: None)


def attach(
    ctx: execution_lib.Context | execution_lib.ContextSync,
    result: execution_lib.CallResult,
) -> execution_lib.CallResult:
    """
    Ship deferred work alongside steps, completion, or a parent error.
    """

    from inngest._internal import execution_lib, server_lib, step_lib

    if not ctx._defer_ops:
        return result
    pending = [
        execution_lib.CallResult(step=op, output=None)
        for op in ctx._defer_ops.values()
    ]
    ctx._defer_ops.clear()
    if result.multi is not None:
        return execution_lib.CallResult(multi=[*pending, *result.multi])
    if result.step is not None:
        return execution_lib.CallResult(multi=[*pending, result])
    opcode = server_lib.Opcode.RUN_COMPLETE
    if result.error is not None:
        opcode = (
            server_lib.Opcode.STEP_ERROR
            if errors.is_retriable(result.error)
            else server_lib.Opcode.STEP_FAILED
        )
    terminal = execution_lib.CallResult(
        error=result.error,
        output=result.output,
        step=step_lib.StepInfo(
            id=transforms.hash_step_id("complete"),
            display_name="complete",
            op=opcode,
        ),
    )
    return execution_lib.CallResult(multi=[*pending, terminal])
