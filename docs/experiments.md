# Experiments

Experimental APIs for sticky variant selection and attributed scores. Async and sync handlers support the same behavior.

```python
from inngest.experimental import experiment

selected = await ctx.group.experiment(
    "model-comparison",
    variants={
        "control": lambda: ctx.step.run("baseline", baseline_model),
        "variant": lambda: ctx.step.run("candidate", candidate_model),
    },
    select=experiment.bucket(str(ctx.event.data["user_id"])),
)

await ctx.step.run("record-cost", lambda: client.score_experiment(
    experiment=selected.experiment_ref,
    run_id=ctx.run_id,
    name="cost",
    value=0.02,
))
```

`bucket` hashes a nonempty string using the TypeScript selection algorithm. It supports optional relative `weights={"control": 80, "variant": 20}`. Names are restricted to lowercase ASCII letters/digits, starting with a letter, to keep ordering consistent across languages. Weights must match the variants and have a finite positive total; zero weights are allowed. `fixed("control")` is useful for tests. Run-weighted and custom selectors are not implemented.

The selection step is memoized, then the chosen callback discovers its steps normally. Every variant must invoke a step tool; plain callback side effects would otherwise repeat during replay. A selected variant must remain available for in-flight runs. Model configuration and external side effects still need the usual durable-step discipline.

Persist `selected.experiment_ref.model_dump()` alongside the original run ID for delayed experiment scoring. Reconstruct it with `experiment.ExperimentRef.model_validate(data)`. `score_experiment` writes attribution before the score; these are two non-atomic merges. If a write fails, retry both. Pass the original `run_id` when scoring inside a callback: the current dashboard's experiment detail view requires run-scoped scores. All score calls require an explicit `run_id`.

Automatic AI usage extraction, extended tracing, LLM judges, and `createScorer`/`defer` helpers are outside this implementation. Verify dashboard visibility against your target backend before relying on a customer demo.
