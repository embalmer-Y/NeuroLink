# Release 2.2.6 Plan

## Purpose

Release 2.2.6 starts the long-run autonomy and self-optimization line on top of the promoted release-2.2.5 persona-governance baseline. The release is intentionally additive: inherited 2.2.4/2.2.5 gates remain green, while 2.2.6 adds deterministic evidence for heartbeat/task tracking, memory maintenance, self-optimization boundaries, World Model v1 context, and staged soak readiness.

## Scope

1. Heartbeat and active-hour configuration for `core-daemon` evidence.
2. Durable task tracking and replay-buffer evidence for interrupted long-running work.
3. Auditable memory maintenance with stale-context summaries and privacy-safe consolidation.
4. Approved self-optimization boundary for low-risk changes, with evidence binding and no autonomous apply/commit/push/deploy.
5. World Model v1 context for temporal incidents, Unit location/capability context, relay relationships, and prompt-safe summaries.
6. Staged soak plan and evidence hooks for developer, release-candidate, and promotion soaks when hardware/social credentials are stable.

## Non-Goals

1. No release identity promotion before all 2.2.6 gates and soak evidence are green.
2. No autonomous repository mutation, commit, push, firmware flash, credential change, or production deploy.
3. No Unit runtime implementation expansion for recovery, gateway route/relay, or state registry unless release owner explicitly promotes those gaps into this release.
4. No new live social compliance claim beyond inherited 2.2.2/2.2.3 evidence.

## New Evidence Commands

1. `task-tracking-smoke`: records active-hour configuration, heartbeat linkage, task records, replay buffer, and rerun-ready cleanup summary.
2. `memory-maintenance-smoke`: records stale-context candidates, prompt-safe consolidation, privacy scopes, and audit binding.
3. `self-optimization-smoke`: records low-risk proposal classification, approval requirement, verified evidence, prohibited actions, and no direct apply boundary.
4. `world-model-context-smoke`: records temporal incidents, Unit location/capability context, relay context, and prompt-safe Affective/Rational summaries.
5. `release-2.2.6-closure-smoke`: inherits the green release-2.2.4/2.2.5 closure lineage and adds the new 2.2.6 gates.
6. `closure-summary --task-tracking-file --memory-maintenance-file --self-optimization-file --world-model-context-file`: folds the additive 2.2.6 evidence into the standard release closure matrix and bundle checklist.
7. `release-2.2.6-live-rerun-template`: emits the bounded hardware/social rerun backlog that should replace inherited 2.2.5 live evidence before promotion.
8. `release-2.2.6-real-unit-rerun-archive`: upgrades `R226-SOC-01` from template-only into a concrete archived real Unit continuity bundle with live-event evidence, coding-agent route evidence, and `real-scene-e2e` closure evidence.
9. `release-2.2.6-qq-gateway-rerun-archive`: upgrades `R226-SOC-02` from template-only into a concrete archived QQ gateway rerun bundle with raw run payload plus closure payload.
10. `release-2.2.6-wecom-gateway-rerun-archive`: upgrades `R226-SOC-03` from template-only into a concrete archived WeCom gateway rerun bundle with raw run payload plus closure payload.
11. `release-2.2.6-openclaw-gateway-rerun-archive`: upgrades `R226-SOC-04` from template-only into a concrete archived OpenClaw gateway rerun bundle with raw run payload plus closure payload.
12. `release-2.2.6-promotion-checklist`: emits a machine-readable promotion-facing review bundle that confirms closure smoke, required rerun rows, conditional rerun rows, and operator-boundary preservation before any identity promotion discussion.
13. `release-2.2.6-hardware-rerun-archive`: upgrades `R226-HW-01` and `R226-HW-02` into a concrete archived hardware rerun bundle with budget/signing evidence plus guarded rollback operator evidence.

## Gates

1. `inherited_release_224_gate`: inherited release-2.2.4/2.2.5 closure lineage remains green.
2. `autonomy_heartbeat_gate`: inherited daemon heartbeat is present and task evidence records active-hour configuration.
3. `task_tracking_replay_gate`: task records, replay buffer, interruption resume, and cleanup readiness are recorded.
4. `memory_maintenance_gate`: stale-context consolidation is audit-bound and prompt-safe.
5. `self_optimization_gate`: self-optimization remains approved, evidence-bound, and unable to apply changes directly.
6. `world_model_context_gate`: temporal incident and Unit context are available without exposing raw private relationship payloads.

## Validation

Focused validation starts with:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m pytest neurolink_core/tests/test_neurolink_core.py -q -k 'task_tracking_smoke or memory_maintenance_smoke or self_optimization_smoke or world_model_context_smoke or release_226_closure_smoke'
```

After generic closure-summary integration, also run:

```bash
python3 -m pytest -q neurolink_core/tests/test_neurolink_core.py -k 'closure_summary_exposes_release_validation_gate_matrix_when_evidence_is_supplied or release_224_closure_smoke_reports_full_green_summary or release_226_closure_smoke_reports_additive_gates or release_226_closure_smoke_can_export_evidence_bundle or task_tracking_smoke_reports_replay_and_cleanup_evidence or memory_maintenance_smoke_reports_prompt_safe_consolidation or self_optimization_smoke_reports_no_direct_apply_boundary or world_model_context_smoke_reports_prompt_safe_context'
```

After the live rerun template slice, also run:

```bash
python3 -m pytest -q neurolink_core/tests/test_neurolink_core.py -k 'release_226_closure_smoke_reports_additive_gates or release_226_closure_smoke_can_export_evidence_bundle or release_226_live_rerun_template_emits_hardware_and_social_rows'
```

After the first concrete rerun archive slice, also run:

```bash
python3 -m pytest -q neurolink_core/tests/test_neurolink_core.py -k 'release_226_closure_smoke_reports_additive_gates or release_226_closure_smoke_can_export_evidence_bundle or release_226_live_rerun_template_emits_hardware_and_social_rows or release_226_real_unit_rerun_archive or release_226_qq_gateway_rerun_archive or release_226_wecom_gateway_rerun_archive or release_226_openclaw_gateway_rerun_archive or release_226_hardware_rerun_archive'
```

After the promotion-facing review slice, also run:

```bash
python3 -m pytest -q neurolink_core/tests/test_neurolink_core.py -k 'release_226_promotion_checklist or release_226_closure_smoke_reports_additive_gates or release_226_closure_smoke_can_export_evidence_bundle'
```

Before promotion, run the full `neurolink_core` and `neuro_cli` suites, then archive staged soak evidence under `smoke-evidence/release-2.2.6-*`.

## Promotion Boundary

Release identity remains `2.2.5` until the final 2.2.6 closure bundle is green, soak evidence is accepted, README/runbooks are updated, and focused plus full regressions pass.
