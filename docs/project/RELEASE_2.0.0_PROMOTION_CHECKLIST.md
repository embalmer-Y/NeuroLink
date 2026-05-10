# Release 2.0.0 Promotion Checklist

## Decision

Status: `promoted`

Date: 2026-05-10

Decision owner: release operator with GitHub Copilot evidence preparation

Release identity is promoted from `1.2.7` to `2.0.0` after the fresh promotion bundle passed all frozen validation gates.

## Evidence

Promotion bundle:

```text
smoke-evidence/release-2.0.0-promotion-20260510T044228Z/
```

Required closure summaries:

1. `closure-summary-final.json`: `validation_gate_summary.ok=true`, `passed_count=20`, `failed_gate_ids=[]` before identity promotion.
2. `closure-summary-post-promotion.json`: `validation_gate_summary.ok=true`, `passed_count=20`, `failed_gate_ids=[]` after identity promotion and post-promotion artifact evidence refresh.

Post-promotion identity evidence:

1. `system-capabilities-post-promotion.json` reports `release_target=2.0.0`.
2. `hardware-compatibility-post-promotion.json` records source identity `app_version=2.0.0` and `build_id=neuro_unit_app-2.0.0-cbor-v2`.
3. `signing-provenance-smoke-post-promotion.json` records source identity `app_version=2.0.0` and `build_id=neuro_unit_app-2.0.0-cbor-v2`.
4. Rebuilt LLEXT artifact: `/home/emb/project/zephyrproject/build/neurolink_unit_app/neuro_unit_app.llext`.

## Validation

1. Neuro CLI focused regression: `127 passed`.
2. AI Core focused regression: `122 passed, 3 subtests passed`.
3. Full Python regression: `367 passed, 6 subtests passed`.
4. Post-promotion closure summary: `20/20` gates passed.

## Promoted Surfaces

1. `neuro_cli/src/neuro_cli.py`: `RELEASE_TARGET = "2.0.0"`.
2. `neuro_cli/src/neuro_workflow_catalog.py`: `RELEASE_TARGET = "2.0.0"`.
3. `subprojects/neuro_unit_app/src/main.c`: app version, build id, and manifest version set to `2.0.0`.
4. README and runbooks describe release `2.0.0` as the promoted baseline.

## Residual Constraints

The stable evidence schema names remain at their frozen `1.2.x` versions where applicable. This is intentional per the release-2.0.0 contract freeze: `2.0.0` is the promoted product identity, not a forced schema renaming pass.
