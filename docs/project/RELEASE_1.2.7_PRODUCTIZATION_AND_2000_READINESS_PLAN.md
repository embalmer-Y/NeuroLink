# Release 1.2.7 Productization And Release-2.0.0 Readiness Plan

## 1. Overview

Release 1.2.7 is the active productization hardening line between the closed
release-1.2.6 federation/relay/Agent platform baseline and the final
release-2.0.0 stabilization and promotion phase.

Its purpose is to close the remaining HLD debt that should not leak into
release-2.0.0 as hidden implementation work:

1. multi-board and multi-artifact acceptance evidence;
2. stronger release, rollback, and approval policy hardening;
3. resource budget governance and enforceable operational ceilings;
4. signing, artifact provenance, and compatibility enforcement maturation;
5. observability, failure diagnosis, and acceptance runbook completion;
6. final release-gate packaging so release-2.0.0 can focus on freeze,
   compatibility, migration notes, and promotion.

Release 1.2.7 must preserve the same architectural rule as 1.2.6: shared Core
and Unit contracts remain hardware-agnostic and capability-driven. Current lab
board paths may be used for bounded validation evidence, but they must not turn
into shared runtime assumptions.

## 2. Position In The Burn-Down

1. release-1.2.5 closed the multimodal Agent runtime and governance baseline.
2. release-1.2.6 closed federation, relay, hardware-abstraction, and governed
   Tool/Skill/MCP quality.
3. release-1.2.7 closes productization hardening and acceptance readiness.
4. release-2.0.0 is then limited to stabilization, compatibility freeze,
   migration notes, final evidence refresh, and explicit version promotion.

Target outcomes for release-1.2.7:

- HLD completion: about 98%.
- Remaining 2.0.0 work: API freeze, compatibility review, migration guidance,
  final acceptance rerun, and promotion approval.

## 3. Carryover From Release 1.2.6

Release-1.2.7 assumes the following 1.2.6 surfaces are already executable:

1. federation topology, delegated execution, and relay route evidence;
2. hardware-abstraction and artifact-compatibility closure gates;
3. governed Tool/Skill/MCP plan-quality enforcement;
4. release-level closure-summary validation matrix;
5. bounded real-board smoke and compatibility evidence on the current baseline.

The remaining debt entering 1.2.7 is not architecture discovery. It is
productization hardening, matrix coverage, operator acceptance, and release
safety.

## 4. Fixed Decisions

1. Canonical release identity remains 1.2.6 during 1.2.7 implementation and is
   promoted only after release-1.2.7 closure evidence passes and promotion is
   explicitly approved.
2. No shared Core or Unit abstraction may encode a single board family, router
   endpoint, PSRAM size, Wi-Fi setup, SD-card layout, or lab-only artifact path
   as a release requirement.
3. Signing and provenance checks must become stricter, but they still remain
   Core-governed and audit-visible rather than hidden inside ad hoc scripts.
4. Multi-board evidence may use staged board families and artifact matrices, but
   failures must degrade into explicit compatibility or acceptance findings
   rather than silent skips.
5. Release and rollback hardening must preserve the existing approval, lease,
   cleanup, and audit boundaries.

## 5. Workstreams

### WS-1 Multi-Board Acceptance Matrix

1. Define the minimum supported board and artifact matrix for release-2.0.0.
2. Record capability and artifact-admission evidence across representative
   board families rather than a single validation board.
3. Keep the matrix bounded and operator-runnable; do not require a full farm.

### WS-2 Resource Budget Governance

1. Turn heap, stack, app-slot, and staging budgets into governed release
   thresholds rather than best-effort evidence.
2. Record acceptance and rejection outcomes as explicit closure evidence.
3. Separate build-time candidate tuning from promoted runtime defaults.

### WS-3 Release And Rollback Hardening

1. Tighten release, activate, rollback, and cleanup runbooks.
2. Expand approval-visible rollback and lease-cleanup evidence.
3. Ensure release/rollback failure states produce explicit operator actions.

### WS-4 Signing And Provenance Enforcement

1. Strengthen signing/provenance expectations for promoted artifacts.
2. Keep compatibility rejection visible before load or activation.
3. Avoid claiming full production PKI if the project is not ready for it.

### WS-5 Observability And Failure Diagnosis

1. Standardize bounded runtime observability for acceptance closure.
2. Improve operator-facing evidence for degraded, relay-failed, unreachable, and
   rollback-required states.
3. Keep all diagnostics structured and release-gate consumable.

### WS-6 Acceptance Documentation And Runbooks

1. Finalize English and Chinese acceptance runbooks for setup, smoke,
   federation/relay fallback, hardware compatibility, and rollback handling.
2. Align README, release plans, progress ledger, AI Core LLD, and Unit LLD.
3. Prepare migration and operator handoff notes for 2.0.0.

### WS-7 Final Regression And Closure Packaging

1. Re-run focused inherited regressions from 1.2.4, 1.2.5, and 1.2.6.
2. Materialize a final release-1.2.7 closure bundle with documentation,
   provider, multimodal, regression, hardware, and route evidence.
3. Enter release-2.0.0 only when the remaining work is stabilization-only.

## 6. Validation Gates

Release-1.2.7 cannot close until all gates pass:

1. Documentation and acceptance gate.
2. Multi-board hardware matrix gate.
3. Resource budget governance gate.
4. Release and rollback hardening gate.
5. Signing and provenance gate.
6. Observability and failure-diagnosis gate.
7. Inherited regression gate.
8. Closure-summary gate.

## 7. Exit Criteria

Release-1.2.7 is complete when:

1. remaining HLD work is explicitly assigned to release-1.2.7 and no longer
   leaks into release-2.0.0 implicitly;
2. the project has a bounded acceptance matrix across representative hardware
   and artifact classes;
3. release/rollback safety and acceptance runbooks are executable and audited;
4. closure-summary can report a clean release matrix for the 1.2.7 bundle;
5. release-2.0.0 can be treated as a stabilization and promotion release.
