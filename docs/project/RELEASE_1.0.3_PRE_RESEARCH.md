# NeuroLink Release 1.0.3 Pre-Research Baseline

## 1. Objective

This document defines the executable pre-research baseline for Release 1.0.3.
The goal is to reduce delivery risk before implementation scale-up by freezing scope,
hardening lease/recovery reliability, and upgrading test/CI evidence quality.

## 2. Scope Decision

### 2.1 In scope

1. Stability and recovery chain hardening for lease and recovery seed paths.
2. UT and CI capability uplift with explicit evidence contracts.
3. Documentation and release-process standardization for repeatable slices.
4. `demo_unit` retirement planning (compatibility freeze and migration mapping).

### 2.2 Out of scope

1. New feature expansion not linked to reliability, testability, or governance.
2. Performance optimization as a primary stream (track as opportunity only).

## 3. Risk-Driven Workstreams

### WS-A: Lease and recovery reliability

Targets:

1. Define failure-mode matrix for lease ownership, priority preemption, and expiry edges.
2. Extend recovery-seed persistence rules for schema/migration safety.
3. Establish evidence for interruption scenarios (missing artifact, corrupted seed, partial transition).

Primary code focus:

1. `applocation/NeuroLink/neuro_unit/src/neuro_lease_manager.c`
2. `applocation/NeuroLink/neuro_unit/src/neuro_recovery_seed_store.c`
3. `applocation/NeuroLink/neuro_unit/src/neuro_artifact_store.c`

### WS-B: UT and CI execution quality

Targets:

1. Create a layered gate model: UT -> component checks -> board smoke evidence.
2. Standardize Windows trigger + WSL/Linux runtime path for canonical UT evidence.
3. Align style gate and runtime gate in one release checklist.

Primary process anchors for the existing Unit UT target:

1. Windows-to-WSL UT trigger: `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_from_windows.ps1`
2. Unit UT execution guide: `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
3. Board-level smoke path: `applocation/NeuroLink/scripts/smoke_neurolink_windows.ps1`

### WS-C: Release governance and documentation

Targets:

1. Freeze 1.0.3 include/exclude boundaries.
2. Require slice-level records: linked LLD section, commands, evidence path, rollback notes.
3. Define weekly review gate and completion criteria.

### WS-D: demo_unit retirement plan

Targets:

1. Freeze `demo_unit` for compatibility only.
2. Produce migration map from `demo_unit` calls/scripts to `neuro_unit` equivalents.
3. Define reversible two-stage retirement policy (freeze, then decommission).

## 4. Four-Week Plan

### Week 1: Scope and failure model baseline

1. Lock 1.0.3 include/exclude table.
2. Land lease/recovery failure-mode matrix and required evidence list.
3. Publish weekly gate checklist v1.

### Week 2: Coverage and CI design landing

1. Define branch-coverage uplift plan for three priority modules.
2. Align UT runtime, style gate, and smoke artifacts into one release path.
3. Classify failures by severity and retry policy.

### Week 3: Retirement and doc hardening

1. Complete `demo_unit` migration map and freeze rules.
2. Standardize slice template updates in progress ledger and testing docs.
3. Prepare first end-to-end pilot slice candidate.

### Week 4: Pilot execution and reprioritization

1. Run one full slice from design to archived evidence.
2. Review gaps and rebalance 1.0.3 backlog priorities.
3. Publish closure notes for pre-research phase.

## 5. Acceptance Criteria

1. Scope freeze file exists with explicit include/exclude decisions.
2. Each lease/recovery failure mode maps to at least one executable verification item.
3. Priority-module branch coverage targets are measurable and tracked weekly.
4. CI path reliably generates evidence from Windows trigger to Linux runtime logs.
5. `demo_unit` retirement is reversible and documented with rollback conditions.

## 6. Initial Deliverables

1. Pre-research baseline document (this file).
2. Ledger kickoff entry `EXEC-085` with scope and next actions.
3. Week-1 scope freeze and failure-mode matrix draft.

## 7. Evidence Conventions

1. Keep UT runtime evidence under `applocation/NeuroLink/smoke-evidence/ut-runtime/`.
2. Keep smoke evidence under `applocation/NeuroLink/smoke-evidence/`.
3. Every completed slice must record commands, result, and artifact paths.

## 8. Immediate Next Actions

1. Create the 1.0.3 include/exclude scope table and add it to the ledger.
2. Draft lease/recovery failure-mode matrix with UT/smoke mapping.
3. Define coverage targets for the three priority modules and baseline values.
