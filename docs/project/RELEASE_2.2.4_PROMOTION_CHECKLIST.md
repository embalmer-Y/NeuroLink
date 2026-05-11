# Release 2.2.4 Promotion Checklist

## Decision

Status: `promoted`

Date: 2026-05-11

Decision owner: release operator with GitHub Copilot evidence preparation

Release identity is promoted from `2.2.3` to `2.2.4` after the packaged
Tool/Skill/MCP governance and coding-agent closure bundle passed the expanded
30-gate validation matrix.

## Evidence

Promotion bundle:

```text
smoke-evidence/release-2.2.4-promotion-<timestamp>/
```

Required closure summary:

1. `closure-summary.json`: `validation_gate_summary.ok=true`,
   `passed_count=30`, `failed_gate_ids=[]` before identity promotion.

Primary promotion evidence in the bundle:

1. `coding-agent-route.json`
2. `agent-excellence-smoke.json`
3. `real-scene-e2e.json`
4. `documentation-closure.json`
5. `closure-summary.json`

Preferred generation command:

```bash
cd /home/emb/project/zephyrproject/applocation/NeuroLink
source /home/emb/project/zephyrproject/.venv/bin/activate
PYTHONPATH=. python -m neurolink_core.cli release-2.2.4-closure-smoke \
  --evidence-dir smoke-evidence/release-2.2.4-promotion-<timestamp>
```

## Validation

1. Focused AI Core regression: `2 passed, 164 deselected` for the packaged
   release-2.2.4 closure smoke and evidence export slice.
2. Command-level packaged closure run: `ok=true`, `passed_count=30`,
   `failed_gate_ids=[]`, and `exported_file_count=25`.
3. Neuro CLI capabilities after identity promotion report `release_target=2.2.4`.

## Promoted Surfaces

1. `neuro_cli/src/neuro_cli.py`: `RELEASE_TARGET = "2.2.4"`.
2. `neuro_cli/src/neuro_workflow_catalog.py`: `RELEASE_TARGET = "2.2.4"`.
3. `subprojects/neuro_unit_app/src/main.c`: app version, build id, and manifest
   patch set to `2.2.4` and `neuro_unit_app-2.2.4-cbor-v2`.
4. `README.md`, `docs/project/AI_CORE_RUNBOOK.md`, and
   `docs/project/AI_CORE_RUNBOOK_ZH.md` describe release `2.2.4` as the
   promoted baseline and document the packaged closure-smoke evidence flow.

## Residual Constraints

Stable evidence schema names remain at their frozen `1.2.x`, `2.1.0`, `2.2.2`,
`2.2.3`, and `2.2.4` contract versions where already defined. This promotion
changes the product release identity and formalizes the packaged release
closure flow; it does not rename historical evidence schemas.