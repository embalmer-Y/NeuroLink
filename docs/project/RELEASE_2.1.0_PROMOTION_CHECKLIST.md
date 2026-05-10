# Release 2.1.0 Promotion Checklist

## Decision

Status: `promoted`

Date: 2026-05-10

Decision owner: release operator with GitHub Copilot evidence preparation

Release identity is promoted from `2.0.0` to `2.1.0` after the fresh promotion bundle passed the expanded 26-gate validation matrix covering the post-2.0 autonomous/social AI Core surfaces.

## Evidence

Promotion bundle:

```text
smoke-evidence/release-2.1.0-promotion-20260510T090042Z/
```

Required closure summaries:

1. `closure-summary-final.json`: `validation_gate_summary.ok=true`, `passed_count=26`, `failed_gate_ids=[]` before identity promotion.
2. `closure-summary-post-promotion.json`: `validation_gate_summary.ok=true`, `passed_count=26`, `failed_gate_ids=[]` after identity promotion and post-promotion artifact evidence refresh.

Post-promotion identity evidence:

1. `system-capabilities-post-promotion.json` reports `release_target=2.1.0`.
2. `hardware-compatibility-post-promotion.json` records source identity `app_version=2.1.0` and `build_id=neuro_unit_app-2.1.0-cbor-v2`.
3. `signing-provenance-smoke-post-promotion.json` records source identity `app_version=2.1.0` and `build_id=neuro_unit_app-2.1.0-cbor-v2`.
4. Rebuilt LLEXT artifact: `/home/emb/project/zephyrproject/build/neurolink_unit_app/neuro_unit_app.llext`.

## Validation

1. AI Core regression: `258 passed, 6 subtests passed`.
2. Neuro CLI regression: `127 passed`.
3. Full Python regression: `385 passed, 6 subtests passed`.
4. Real provider smoke: `model_call_succeeded`.
5. Post-promotion closure summary: `26/26` gates passed.

## Promoted Surfaces

1. `neuro_cli/src/neuro_cli.py`: `RELEASE_TARGET = "2.1.0"`.
2. `neuro_cli/src/neuro_workflow_catalog.py`: `RELEASE_TARGET = "2.1.0"`.
3. `subprojects/neuro_unit_app/src/main.c`: app version, build id, and manifest version set to `2.1.0`.
4. `README.md`, `docs/project/AI_CORE_RUNBOOK.md`, and `docs/project/AI_CORE_RUNBOOK_ZH.md` describe release `2.1.0` as the promoted baseline.

## Residual Constraints

Stable evidence schema names remain at their frozen `1.2.x` versions where applicable, and the integrated `closure-summary` schema remains `1.2.7-closure-summary-v14`. This is intentional: `2.1.0` is the promoted product identity, not a schema-renaming pass.