# NeuroLink Release 1.0.3 Scope Freeze

## 1. Decision Date

- Date: 2026-04-15
- Version: Release-1.0.3 (pre-research week-1)
- Source ledger: `EXEC-085`

## 2. Include Scope

| ID | Area | Include decision | Rationale | Exit evidence |
| --- | --- | --- | --- | --- |
| INC-01 | Lease lifecycle | Include | Priority preemption, ownership, and expiry edges are high-risk runtime controls. | UT matrix and runtime evidence for normal/error transitions. |
| INC-02 | Recovery seed persistence | Include | Existing branch coverage is low in key fault paths and schema edges. | UT coverage uplift and corruption/interruption tests. |
| INC-03 | Artifact/recovery consistency | Include | Missing/corrupted artifact scenarios can break recovery continuity. | UT for artifact missing/mismatch + smoke trace validation. |
| INC-04 | UT/CI gate integration | Include | Current evidence is available but not fully standardized as release gate contract. | Documented gate order and reproducible logs from canonical scripts. |
| INC-05 | Linux style and release checklist | Include | Style gate is established and must remain in release discipline. | Checklist item with pass/fail trace in each slice. |
| INC-06 | `demo_unit` retirement planning | Include | Need controlled freeze and migration path to avoid dual-maintenance drift. | Migration map and two-stage retirement policy approved. |

## 3. Exclude Scope

| ID | Area | Exclude decision | Revisit condition |
| --- | --- | --- | --- |
| EXC-01 | New feature expansion unrelated to reliability/test/governance | Exclude | Revisit after reliability goals and gate standardization reach target. |
| EXC-02 | Broad architecture rewrite outside lease/recovery boundaries | Exclude | Revisit if week-4 pilot shows structural blocker not solvable incrementally. |
| EXC-03 | Performance as primary stream | Exclude | Revisit after week-2 baseline if critical regression appears. |
| EXC-04 | Immediate hard removal of `demo_unit` | Exclude | Revisit only after freeze period and migration proof is complete. |

## 4. Guardrails

1. Each 1.0.3 slice must map to at least one `INC-*` ID.
2. Any proposal touching `EXC-*` requires explicit ledger note and user sign-off.
3. `demo_unit` accepts only compatibility or retirement actions; no net-new feature logic.

## 5. Week-1 Completion Definition

1. Scope table accepted and linked from the active execution entry.
2. Failure-mode matrix drafted with verification mapping.
3. First coverage target baseline identified for lease/recovery modules.
