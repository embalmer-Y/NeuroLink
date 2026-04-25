# NeuroLink Release 1.1.2 Pre-Research Baseline

## 1. Objective

This document defines the executable pre-research baseline for Release 1.1.2.
The goal is to convert Release 1.1.1 callback/event capabilities from
feature-complete to operator-grade reliable, reproducible, and auditable delivery,
while raising overall code quality and framework maintainability.

## 2. Scope Decision

### 2.1 In scope

1. Standalone multi-process app-event listener reliability hardening.
2. Callback/event observability and diagnosability contract unification.
3. Board-smoke reproducibility uplift for callback listener flows.
4. Release evidence retention policy for callback and smoke artifacts.
5. Focused UT/CLI regression expansion for callback and listener edge paths.
6. Code quality baseline uplift (complexity, duplication, diagnostics consistency).
7. Framework optimization for lower coupling and clearer module ownership.

### 2.2 Out of scope

1. New communication planes, gateway federation, or protocol redesign.
2. App model redesign beyond current invoke + callback configuration contract.
3. Unrelated performance tuning without reliability impact.

## 2.3 Quality and Framework Principles

1. Keep behavior stable first: refactor must preserve protocol and operator contracts.
2. Improve internal quality in small reversible slices: one concern per slice.
3. Prefer measurable quality gates over subjective code cleanup.
4. Keep diagnostics machine-readable and compatible with existing smoke tooling.

## 2.4 Quality Metrics Baseline and Targets

Track these as release-1.1.2 quality KPIs:

1. Unit CLI hot-path function complexity (focus on listener and query-retry flows):
   - Baseline capture in week 1.
   - Target: reduce top 5 complex functions by at least 20 percent.
2. Framework module coupling:
   - Baseline: include and call-graph dependency inventory.
   - Target: remove at least 2 non-essential cross-module dependencies.
3. Regression confidence:
   - Baseline: current UT and CLI tests.
   - Target: add at least 10 negative-path and edge-path tests.
4. Diagnostics quality:
   - Baseline: mixed human/JSON message styles.
   - Target: all new failure paths include stable status and reason fields.

## 3. Baseline from Release 1.1.1 Audit

1. Code-level capabilities are landed:
   - `core_cli.py` release target remains `1.1.1`.
   - `app-callback-config`, `app-events`, and grouped aliases are implemented.
   - Listener strategy declares `fifo_channel` / callback variants with diagnostics.
   - Unit side supports `network_disconnect` and app-event publishing through `neuro_unit_event`.
2. Local executable validation remains green on current workspace:
   - `pytest` for Unit CLI tests passed.
   - Unit native_sim UT run passed.
3. Evidence management gap:
   - callback/smoke evidence directories were intentionally cleaned at release closeout,
     reducing immediate replay traceability for historical signatures.

## 4. Risk-Driven Workstreams

### WS-A: Standalone listener reliability

Targets:

1. Define a deterministic listener-service contract (ready, settle, pump, timeout, shutdown).
2. Validate receive behavior across supported zenoh Python handler variants.
3. Add anti-flake controls and explicit failure signatures for multi-process replay.
4. Isolate listener lifecycle logic from command parsing code to improve testability.

Primary code focus:

1. `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`
2. `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`

### WS-B: Unit event-path robustness

Targets:

1. Keep app-event publication contract strict and testable.
2. Expand negative-path UT for malformed callback config and invalid event naming.
3. Ensure board capability hooks (`network_disconnect`) remain behaviorally stable.
4. Reduce framework-to-port coupling by clarifying ownership boundaries.

Primary code focus:

1. `applocation/NeuroLink/neuro_unit/src/neuro_unit_event.c`
2. `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c`
3. `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
4. `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_neuro_unit_event.c`
5. `applocation/NeuroLink/neuro_unit/tests/unit/src/runtime/test_app_runtime_cmd_capability.c`

### WS-C: Evidence governance and reproducibility

Targets:

1. Define retention tiers for release-closeout cleanup versus audit traceability.
2. Standardize callback-listener evidence bundle format (control log + listener JSON + env metadata).
3. Add one-command replay guidance for two-terminal standalone validation.

### WS-D: Code quality uplift and framework optimization

Targets:

1. Build a quality baseline report for CLI and Unit critical modules.
2. Prioritize high-risk refactor candidates by complexity and change frequency.
3. Standardize error/result envelope shape for CLI and Unit-facing JSON output.
4. Introduce lightweight architecture checks to prevent accidental coupling regressions.

Primary code focus:

1. `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`
2. `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
3. `applocation/NeuroLink/neuro_unit/src/neuro_unit_event.c`
4. `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
5. `applocation/NeuroLink/neuro_unit/tests/unit`

Primary process anchors:

1. `applocation/NeuroLink/PROJECT_PROGRESS.md`
2. `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md`
3. `applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`

## 5. Four-Week Plan

### Week 1: Contract freeze and failure signatures

1. Freeze listener-service behavioral contract and output schema.
2. Enumerate failure signatures for callback replay (no_event, late_event, partial_event).
3. Capture quality baseline (complexity, coupling, diagnostics shape inventory).
4. Land UT updates for parser and listener-mode diagnostics consistency.

### Week 2: Replay hardening and automation

1. Add reproducible two-terminal replay script template.
2. Verify callback replay under router debug and non-debug profiles.
3. Capture first standardized callback evidence bundle.
4. Start first low-risk refactor slice on listener lifecycle extraction.

### Week 3: Evidence policy and documentation convergence

1. Land release evidence retention policy section in project docs.
2. Align smoke runbook with callback listener replay SOP.
3. Define cleanup policy exceptions for latest release verification artifacts.
4. Land framework optimization slice for module boundary cleanup with no behavior change.

### Week 4: Pilot closure and backlog rebalance

1. Execute one full pre-research pilot from code change to archived evidence.
2. Record residual risks and classify 1.1.2 implementation entry slices.
3. Publish pre-research closure notes with go/no-go recommendation.
4. Publish quality delta report (baseline vs current KPIs).

## 5.1 Proposed Execution Slices (Code Quality + Framework)

1. `EXEC-092`: quality baseline capture (complexity, coupling, diagnostics schema map).
2. `EXEC-093`: CLI listener lifecycle extraction with regression-first tests.
3. `EXEC-094`: Unit event and runtime command boundary cleanup.
4. `EXEC-095`: diagnostics and error-envelope normalization.
5. `EXEC-096`: quality gate update and evidence retention policy finalization.

## 6. Acceptance Criteria

1. Standalone callback listener flow has deterministic pass/fail criteria and logs.
2. At least one reproducible callback replay evidence bundle is archived per cycle.
3. UT matrix covers core callback config and listener negative paths.
4. Cleanup policy preserves minimum audit evidence while maintaining repository hygiene.
5. 1.1.2 implementation backlog is split into executable slices with owners.
6. Code quality KPIs show measurable improvement against week-1 baseline.
7. Framework module boundaries are documented and validated by tests/build checks.

## 7. Initial Deliverables

1. Pre-research baseline document (this file).
2. Ledger kickoff update confirming release-1.1.1 code audit status.
3. Initial 1.1.2 workstreams and week-by-week execution baseline.

## 8. Immediate Next Actions

1. Build and archive a quality baseline report for `core_cli.py` and Unit core modules.
2. Draft callback-listener failure-mode matrix and map each mode to UT/smoke checks.
3. Define callback evidence bundle schema (JSON + logs + metadata) and retention tier.
4. Open first implementation slice for listener lifecycle extraction with test-first guardrails.

## 9. Planning Output for Next Step

Use this order for immediate execution:

1. Baseline: complexity + coupling + diagnostics inventory.
2. Safety net: add missing negative-path tests before refactor.
3. Refactor: extract listener lifecycle and normalize error envelopes.
4. Validate: rerun CLI pytest and Unit native_sim UT.
5. Archive: emit quality delta and callback evidence bundle summary.
