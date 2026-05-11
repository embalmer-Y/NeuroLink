# Release 2.2.5 Promotion Checklist

## Decision

Status: `promoted`

Date: 2026-05-11

Decision owner: release operator with GitHub Copilot evidence preparation

Release identity is promoted from `2.2.4` to `2.2.5` after the bounded
persona-governance scope closed green. This release formalizes first-class
persona seed setup, runtime-evidence-only growth apply, read-only inspect,
privacy export/delete, and immutability/tamper reporting on top of the already
green release-2.2.4 governance baseline.

## Evidence

Primary bounded evidence:

1. focused `neurolink_core` persona-governance regressions
2. focused `closure-summary` regressions carrying the additive 2.2.5 gates
3. focused `neuro_cli` release-target and sample-app identity regressions
4. `PROJECT_PROGRESS.md` execution ledger entries `EXEC-386` and `EXEC-387`

## Validation

1. Focused AI Core persona and closure regression:
   `10 passed, 165 deselected`.
2. Focused Neuro CLI release-target regression:
   `3 passed, 124 deselected` for:
   - `test_workflow_commands_do_not_embed_release_target_literals`
   - `test_sample_app_source_identity_matches_release_target`
   - `test_capabilities_reports_current_release_target`
3. No new whitespace issues in the promoted files.

## Promoted Surfaces

1. `neuro_cli/src/neuro_cli.py`: `RELEASE_TARGET = "2.2.5"`.
2. `neuro_cli/src/neuro_workflow_catalog.py`: `RELEASE_TARGET = "2.2.5"`.
3. `subprojects/neuro_unit_app/src/main.c`: app version, build id, and manifest
   patch set to `2.2.5` and `neuro_unit_app-2.2.5-cbor-v2`.
4. `README.md`, `docs/project/AI_CORE_RUNBOOK.md`, and
   `docs/project/AI_CORE_RUNBOOK_ZH.md` describe release `2.2.5` as the current
   completed persona-governance baseline.

## Residual Constraints

Stable evidence schema names remain at their inherited `1.2.x`, `2.1.0`,
`2.2.2`, `2.2.3`, `2.2.4`, and additive `2.2.5` contract versions where
already defined. This promotion changes the product release identity and marks
the bounded repository state complete; it does not introduce a new packaged
release-2.2.5 closure-smoke command or claim release-2.2.6 closure.