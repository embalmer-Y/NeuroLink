# Release 2.2.6 Promotion Checklist

## Decision

Status: `development_complete_not_promoted`

Date: 2026-05-11

Decision owner: release operator with GitHub Copilot evidence preparation

The planned release-2.2.6 development content is complete and archived, but
release identity remains `2.2.5`. This checklist records a bounded completion
state for the 2.2.6 autonomy, memory-maintenance, self-optimization,
world-model, rerun-archive, and promotion-review surfaces while preserving the
existing promotion boundary: no release identity change until staged soak
evidence is accepted.

## Evidence

Finalization bundle:

```text
smoke-evidence/release-2.2.6-finalization-20260511T123307Z/
```

Primary archived evidence in the bundle:

1. `release-2.2.6-promotion-checklist.json`
2. `release-2.2.6-closure-smoke.json`
3. `release-2.2.6-live-rerun-template.json`
4. `promotion-checklist-output.json`

Primary implementation records outside the bundle:

1. `PROJECT_PROGRESS.md` execution ledger entries `EXEC-388` through `EXEC-393`
2. `docs/project/RELEASE_2.2.6_PLAN.md`
3. `neurolink_core/cli.py` additive 2.2.6 evidence commands and checklist entrypoint

## Validation

1. Full AI Core regression: `364 passed, 6 subtests passed`.
2. Full Neuro CLI regression: `138 passed`.
3. Focused promotion-review regression: `4 passed, 190 deselected` for the
   release-2.2.6 promotion checklist and closure-smoke slice.
4. No new whitespace issues in the finalized files.

## Completed Surfaces

1. `task-tracking-smoke`, `memory-maintenance-smoke`,
   `self-optimization-smoke`, and `world-model-context-smoke` close the new
   additive 2.2.6 governance gates.
2. `release-2.2.6-closure-smoke` packages the inherited 2.2.4/2.2.5 closure
   lineage with the additive 2.2.6 gates.
3. `release-2.2.6-live-rerun-template` defines the bounded hardware and social
   rerun backlog for promotion review.
4. `release-2.2.6-real-unit-rerun-archive`,
   `release-2.2.6-qq-gateway-rerun-archive`,
   `release-2.2.6-wecom-gateway-rerun-archive`,
   `release-2.2.6-openclaw-gateway-rerun-archive`, and
   `release-2.2.6-hardware-rerun-archive` convert every planned rerun row into
   a concrete archive contract.
5. `release-2.2.6-promotion-checklist` provides a machine-readable operator
   review surface for required rows, conditional rows, archive readiness, and
   preserved approval boundaries.

## Residual Constraints

Canonical release identity remains `2.2.5`; this checklist does not promote
the product release target. Staged soak evidence and explicit release-owner
acceptance are still required before any future identity promotion. Stable
schema versions remain on their inherited `1.2.x`, `2.1.0`, `2.2.2`, `2.2.3`,
`2.2.4`, `2.2.5`, and additive `2.2.6` contract lines where already defined.