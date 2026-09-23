"""
Experimental, replay-stable experiment selection and attribution.

The API may change without a major version bump. Bucket keys must be non-empty
strings. Bucket variant names use lowercase ASCII letters/digits so ordering
is identical to TypeScript's locale-sorted variant names.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import re
import typing

from inngest._internal import errors, run_context
from inngest._internal.scores import ExperimentRef

T = typing.TypeVar("T")


def _valid_name(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_weight(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= 0
    )


@dataclasses.dataclass(frozen=True)
class ExperimentResult(typing.Generic[T]):
    """Variant output and a reference that can be persisted for later scoring."""

    result: T
    variant: str
    experiment_ref: ExperimentRef


@dataclasses.dataclass(frozen=True)
class Selection:
    """A validated, immutable selection strategy."""

    strategy: typing.Literal["fixed", "bucket"]
    value: str
    weights: tuple[tuple[str, float], ...] | None = None

    def choose(self, names: list[str]) -> str:
        """Select a known variant with TypeScript-compatible bucket hashing."""
        if self.strategy == "fixed":
            selected = self.value
        else:
            if any(
                re.fullmatch(r"[a-z][a-z0-9]*", name) is None for name in names
            ):
                raise ValueError(
                    "Bucket variant names must use lowercase ASCII letters and digits, starting with a letter"
                )
            weights = (
                dict(self.weights)
                if self.weights is not None
                else dict.fromkeys(names, 1.0)
            )
            if set(weights) != set(names):
                raise ValueError(
                    "Experiment weights must match the variant names"
                )
            entries = sorted(weights.items())
            fraction = (
                int(
                    hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:8],
                    16,
                )
                / 0x100000000
            )
            total = sum(weights.values())
            cursor = 0.0
            selected = entries[-1][0]
            for name, weight in entries:
                cursor += weight / total
                if fraction < cursor:
                    selected = name
                    break
        if selected not in names:
            raise errors.NonRetriableError(
                f"Experiment selected unknown variant {selected!r}"
            )
        return selected


def fixed(variant: str) -> Selection:
    """Always select a named variant; useful for controlled comparisons."""
    if not _valid_name(variant):
        raise ValueError("Variant must be a non-empty string")
    return Selection("fixed", variant)


def bucket(
    value: str, *, weights: typing.Mapping[str, float] | None = None
) -> Selection:
    """Assign a stable user ID to a variant, optionally using relative weights."""
    if not _valid_name(value):
        raise ValueError("Bucket key must be a non-empty string")
    snapshot = None
    if weights is not None:
        if any(not _valid_weight(weight) for weight in weights.values()):
            raise ValueError("Weights must be finite non-negative numbers")
        total = sum(weights.values())
        if not math.isfinite(total) or total <= 0:
            raise ValueError("Weights must have a finite positive total")
        snapshot = tuple(weights.items())
    return Selection("bucket", value, snapshot)


def _validate(
    experiment_id: str, variants: typing.Mapping[str, object]
) -> None:
    if not _valid_name(experiment_id):
        raise ValueError("Experiment ID must be a non-empty string")
    if not variants or any(
        not _valid_name(name) or not callable(callback)
        for name, callback in variants.items()
    ):
        raise ValueError("Experiments require named variant callbacks")
    if run_context.current_run.get() is None:
        raise ValueError("Experiments require an Inngest function execution")
    if run_context.current_step.get() is not None:
        raise errors.NonRetriableError(
            "Experiments cannot be nested inside a step callback"
        )


def _select(experiment_id: str, names: list[str], select: Selection) -> str:
    selected = select.choose(names)
    step = run_context.current_step.get()
    if step is None:
        raise RuntimeError("Missing experiment selection step")
    values: dict[str, object] = {
        "name": experiment_id,
        "variant": selected,
        "selection_strategy": select.strategy,
        "available_variants": names,
    }
    if select.weights is not None:
        values["variant_weights"] = dict(select.weights)
    step.metadata.append(
        {
            "kind": "inngest.experiment",
            "scope": "step",
            "op": "merge",
            "values": values,
        }
    )
    return selected


def _variant_context(
    experiment_id: str, selected: str, select: Selection, hashed_id: str
) -> run_context.ExperimentContext:
    return run_context.ExperimentContext(
        {
            "experimentStepID": hashed_id,
            "experimentName": experiment_id,
            "variant": selected,
            "selectionStrategy": select.strategy,
        }
    )


async def _run(
    experiment_id: str,
    variants: typing.Mapping[str, typing.Callable[[], typing.Awaitable[T]]],
    select: Selection,
) -> ExperimentResult[T]:
    from inngest._internal.step_lib import Step

    _validate(experiment_id, variants)
    run = run_context.current_run.get()
    if run is None or not isinstance(run.ctx.step, Step):
        raise ValueError("Async experiments require an async function")
    hashed_id = ""

    async def choose() -> str:
        nonlocal hashed_id
        selected = _select(experiment_id, list(variants), select)
        step = run_context.current_step.get()
        if step is not None:
            hashed_id = step.id
        return selected

    selected = await run.ctx.step._run(
        experiment_id, choose, step_type="group.experiment"
    )
    if selected not in variants:
        raise errors.NonRetriableError(
            f"Memoized experiment variant {selected!r} is no longer defined"
        )
    ctx = _variant_context(experiment_id, selected, select, hashed_id)
    token = run_context.current_experiment.set(ctx)
    try:
        result = await variants[selected]()
        if not ctx.found_step:
            raise errors.NonRetriableError(
                "Experiment variants must invoke step tools to avoid replaying side effects"
            )
        return ExperimentResult(
            result,
            selected,
            ExperimentRef(experiment_name=experiment_id, variant=selected),
        )
    finally:
        run_context.current_experiment.reset(token)


def _run_sync(
    experiment_id: str,
    variants: typing.Mapping[str, typing.Callable[[], T]],
    select: Selection,
) -> ExperimentResult[T]:
    from inngest._internal.step_lib import StepSync

    _validate(experiment_id, variants)
    run = run_context.current_run.get()
    if run is None or not isinstance(run.ctx.step, StepSync):
        raise ValueError("Sync experiments require a sync function")
    hashed_id = ""

    def choose() -> str:
        nonlocal hashed_id
        selected = _select(experiment_id, list(variants), select)
        step = run_context.current_step.get()
        if step is not None:
            hashed_id = step.id
        return selected

    selected = run.ctx.step._run(
        experiment_id, choose, step_type="group.experiment"
    )
    if selected not in variants:
        raise errors.NonRetriableError(
            f"Memoized experiment variant {selected!r} is no longer defined"
        )
    ctx = _variant_context(experiment_id, selected, select, hashed_id)
    token = run_context.current_experiment.set(ctx)
    try:
        result = variants[selected]()
        if not ctx.found_step:
            raise errors.NonRetriableError(
                "Experiment variants must invoke step tools to avoid replaying side effects"
            )
        return ExperimentResult(
            result,
            selected,
            ExperimentRef(experiment_name=experiment_id, variant=selected),
        )
    finally:
        run_context.current_experiment.reset(token)


__all__ = ["ExperimentRef", "ExperimentResult", "Selection", "bucket", "fixed"]
