# Backend follow-up: experiment assignment conflicts

Each `(run_id, step_id)` target stores one experiment assignment while scores accumulate by metric name. Scoring `model/accuracy`, then `prompt/quality` on the same target silently attributes both scores to `prompt`. Changing the variant has the same risk.

The metadata API currently accepts unconditional merges. SDK-side reads or locks cannot prevent conflicts across processes, retries, and concurrent scorers. Separate experiment targets avoid collisions, but step-scoped scores are not shown in the current experiment detail view.

Add atomic backend conflict detection: accept identical assignments for retries; reject a different experiment name or variant before changing attribution or scores. Cover sequential conflicts, concurrent conflicting writes, and retries after partial failure. This work is outside the Python SDK PR.
