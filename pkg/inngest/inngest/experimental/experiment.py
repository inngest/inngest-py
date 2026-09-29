"""
Experimental, replay-stable experiment selection and attribution.

The API may change without a major version bump. Bucket keys must be non-empty
strings. Bucket variant names use lowercase ASCII letters/digits so ordering
is identical to TypeScript's locale-sorted variant names.
"""

from __future__ import annotations

import contextlib
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
    """
    Return type of fixed() and bucket(), available for type annotations.

    Use those factories to create selectors. Construction and fields are
    implementation details.
    """

    strategy: typing.Literal["fixed", "bucket"]
    value: str
    weights: tuple[tuple[str, float], ...] | None = None

    def __post_init__(self) -> None:
        """Validate direct construction and snapshot weights before use."""
        if self.strategy not in ("fixed", "bucket"):
            raise ValueError("Selection strategy must be fixed or bucket")
        if not _valid_name(self.value):
            raise ValueError("Selection value must be a non-empty string")
        if self.weights is None:
            return
        if self.strategy != "bucket":
            raise ValueError("Only bucket selection accepts weights")
        weights = tuple((name, weight) for name, weight in self.weights)
        if any(not _valid_weight(weight) for _, weight in weights):
            raise ValueError("Weights must be finite non-negative numbers")
        if len(dict(weights)) != len(weights):
            raise ValueError("Variant weights must have unique names")
        total = sum(weight for _, weight in weights)
        if not math.isfinite(total) or total <= 0:
            raise ValueError("Weights must have a finite positive total")
        object.__setattr__(self, "weights", weights)

    def choose(self, names: list[str]) -> str:
        """Select a known variant with TypeScript-compatible bucket hashing."""
        if self.strategy == "fixed":
            selected = self.value
        else:
            if any(
                re.fullmatch(r"[a-z][a-z0-9]*", name) is None for name in names
            ):
                raise errors.NonRetriableError(
                    "Bucket variant names must use lowercase ASCII letters and digits, starting with a letter"
                )
            weights = (
                dict(self.weights)
                if self.weights is not None
                else dict.fromkeys(names, 1.0)
            )
            if set(weights) != set(names):
                raise errors.NonRetriableError(
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
    return Selection("fixed", variant)


def bucket(
    value: str, *, weights: typing.Mapping[str, float] | None = None
) -> Selection:
    """Assign a stable user ID to a variant, optionally using relative weights."""
    return Selection(
        "bucket", value, tuple(weights.items()) if weights is not None else None
    )


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
    if run_context.current_experiment.get() is not None:
        raise errors.NonRetriableError("Nested experiments are not supported")
    if run_context.current_step.get() is not None:
        raise errors.NonRetriableError(
            "Experiments cannot be nested inside a step callback"
        )


def _select(
    experiment_id: str, names: list[str], select: Selection
) -> dict[str, str]:
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
    # Keep attribution tied to the original selection across configuration changes.
    return {"variant": selected, "strategy": select.strategy}


@contextlib.contextmanager
def _variant_context(
    experiment_id: str, selected: str, strategy: str
) -> typing.Iterator[None]:
    """Bind variant attribution and require durable work on normal completion."""
    ctx = run_context.ExperimentContext(
        {
            "experimentName": experiment_id,
            "variant": selected,
            "selectionStrategy": strategy,
        }
    )
    token = run_context.current_experiment.set(ctx)
    try:
        yield
        if not ctx.found_step:
            raise errors.NonRetriableError(
                "Experiment variants must invoke step tools to avoid replaying side effects"
            )
    finally:
        run_context.current_experiment.reset(token)


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

    async def choose() -> dict[str, str]:
        return _select(experiment_id, list(variants), select)

    assignment = await run.ctx.step._run(
        experiment_id, choose, step_type="group.experiment"
    )
    selected = assignment["variant"]
    if selected not in variants:
        raise errors.NonRetriableError(
            f"Memoized experiment variant {selected!r} is no longer defined"
        )
    with _variant_context(experiment_id, selected, assignment["strategy"]):
        result = await variants[selected]()
        return ExperimentResult(
            result,
            selected,
            ExperimentRef(experiment_name=experiment_id, variant=selected),
        )


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

    def choose() -> dict[str, str]:
        return _select(experiment_id, list(variants), select)

    assignment = run.ctx.step._run(
        experiment_id, choose, step_type="group.experiment"
    )
    selected = assignment["variant"]
    if selected not in variants:
        raise errors.NonRetriableError(
            f"Memoized experiment variant {selected!r} is no longer defined"
        )
    with _variant_context(experiment_id, selected, assignment["strategy"]):
        result = variants[selected]()
        return ExperimentResult(
            result,
            selected,
            ExperimentRef(experiment_name=experiment_id, variant=selected),
        )


__all__ = ["ExperimentRef", "ExperimentResult", "bucket", "fixed"]
