# Release 2.2.3 Promotion Checklist

## Decision

Status: `promoted`

Date: 2026-05-11

Decision owner: release operator with GitHub Copilot evidence preparation

Release identity is promoted from `2.2.2` to `2.2.3` after the fresh
OpenClaw-compatible social gateway bundle passed the expanded 29-gate
validation matrix covering direct WeCom and bounded OpenClaw-hosted
compatibility closure.

## Evidence

Promotion bundle:

```text
smoke-evidence/release-2.2.3-promotion-20260511T045344Z/
```

Required closure summary:

1. `closure-summary-final.json`: `validation_gate_summary.ok=true`,
   `passed_count=29`, `failed_gate_ids=[]` before identity promotion.

Primary promotion evidence in the bundle:

1. `wecom-gateway-closure.json`
2. `openclaw-gateway-closure.json`
3. `social-adapter-smoke.json`
4. `regression-closure.json`
5. `documentation-closure.json`

## Validation

1. Release-2.2.3 packaged pre-promotion validation: `9 passed, 35 deselected`
   for the social slice and `3 passed, 156 deselected` for the closure slice.
2. Final bundle closure summary: `29/29` gates passed.
3. Neuro CLI capabilities after identity promotion report `release_target=2.2.3`.

## Promoted Surfaces

1. `neuro_cli/src/neuro_cli.py`: `RELEASE_TARGET = "2.2.3"`.
2. `neuro_cli/src/neuro_workflow_catalog.py`: `RELEASE_TARGET = "2.2.3"`.
3. `subprojects/neuro_unit_app/src/main.c`: app version and build id set to
   `2.2.3` and `neuro_unit_app-2.2.3-cbor-v2`.
4. `README.md`, `docs/project/AI_CORE_RUNBOOK.md`, and
   `docs/project/AI_CORE_RUNBOOK_ZH.md` describe release `2.2.3` as the
   promoted baseline.

## Residual Constraints

Stable evidence schema names remain at their frozen `1.2.x`, `2.1.0`, `2.2.2`,
and `2.2.3` contract versions where already defined. This promotion changes the
product release identity, not the historical evidence-schema lineage.