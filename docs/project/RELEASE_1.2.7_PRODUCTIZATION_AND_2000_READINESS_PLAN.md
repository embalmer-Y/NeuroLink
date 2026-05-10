# Release 1.2.7 HLD Completion And Release-2.0.0 Readiness Plan

## 1. Overview

Release 1.2.7 is now closed as the HLD completion line between the closed
release-1.2.6 federation/relay/Agent platform baseline and the final
release-2.0.0 stabilization and promotion phase. It served as the last
implementation-heavy minor release before 2.0.0, and its archived final bundle
is recorded under `smoke-evidence/release-1.2.7-closure-20260510T040915Z/`.

Its purpose is to close all remaining non-stabilization HLD development work
that should not leak into release-2.0.0 as hidden implementation debt:

1. multi-board and multi-artifact acceptance evidence;
2. stronger release, rollback, and approval policy hardening;
3. resource budget governance and enforceable operational ceilings;
4. signing, artifact provenance, and compatibility enforcement maturation;
5. observability, failure diagnosis, and acceptance runbook completion;
6. Agent Tool, Skill, and MCP excellence beyond the release-1.2.6 safety
   baseline;
7. real neuro_core plus neuro_unit end-to-end scenario evidence;
8. final release-gate packaging so release-2.0.0 can focus on freeze,
   compatibility, migration notes, final scenario reruns, and promotion.

Release 1.2.7 must preserve the same architectural rule as 1.2.6: shared Core
and Unit contracts remain hardware-agnostic and capability-driven. Current lab
board paths may be used for bounded validation evidence, but they must not turn
into shared runtime assumptions. Concrete boards, router endpoints, Wi-Fi
settings, PSRAM sizes, SD-card layouts, and lab artifact paths are evidence
inputs only, never shared contract requirements.

## 2. Position In The Burn-Down

1. release-1.2.5 closed the multimodal Agent runtime and governance baseline.
2. release-1.2.6 closed federation, relay, hardware-abstraction, and governed
   Tool/Skill/MCP quality.
3. release-1.2.7 closes the remaining implementation-bearing HLD surface:
   multi-hardware acceptance, Restricted Unit behavior, Agent Tool/Skill/MCP
   excellence, release safety, signing/provenance, observability, and real
   Core/Unit scenario readiness.
4. release-2.0.0 is then limited to stabilization, compatibility freeze,
   migration notes, final real-scene evidence refresh, and explicit version
   promotion.

Target outcomes for release-1.2.7:

- HLD development completion: about 100% of non-stabilization implementation
   surface.
- HLD completion including final stabilization and promotion work: about 98%.
- Remaining 2.0.0 work: API/contract freeze, compatibility review, migration
   guidance, final full real-scene rerun, and promotion approval.

## 3. Carryover From Release 1.2.6

Release-1.2.7 assumes the following 1.2.6 surfaces are already executable:

1. federation topology, delegated execution, and relay route evidence;
2. hardware-abstraction and artifact-compatibility closure gates;
3. governed Tool/Skill/MCP plan-quality enforcement;
4. release-level closure-summary validation matrix;
5. bounded real-board smoke and compatibility evidence on the current baseline.

The remaining debt entering 1.2.7 is not architecture discovery. It is the last
implementation closure layer: productization hardening, matrix coverage,
operator acceptance, release safety, Agent quality, and real Core/Unit scenario
evidence.

## 3A. HLD Closure Map

| HLD surface | Release-1.2.7 disposition | Release-2.0.0 disposition |
| --- | --- | --- |
| Multi-hardware Unit classes | Close capability-class matrix, board-family mapping, and deterministic plus bounded real evidence. | Final compatibility review and rerun only. |
| Restricted Unit support | Close explicit degraded behavior for non-LLEXT or resource-limited targets. | Stabilization and migration notes only. |
| Gateway, relay, and federation | Reuse 1.2.6 route contracts and add real-scenario acceptance rows. | Final full rerun after freeze. |
| Agent Tool/Skill/MCP quality | Raise from safe governance to product-grade tool discovery, schema discipline, plan repair, and governed MCP UX. | Compatibility review of frozen contracts. |
| Release, rollback, and cleanup | Close failure-mode matrix, approval-visible rollback, lease cleanup, and operator next actions. | Final rerun and migration guidance. |
| Signing and provenance | Close enforceable policy states and pre-admission provenance evidence. | Final policy review and promotion approval. |
| Observability and diagnosis | Close structured degraded/unreachable/relay-failed/rollback-required evidence. | Acceptance rerun and support handoff. |
| Real neuro_core plus neuro_unit integration | Implement and pass deterministic, single-real-Unit, multi-Core, relay, and Agent-assisted scenario harnesses. | Full real-scene rerun before promotion. |
| API and contract freeze | Prepare freeze candidates and compatibility evidence. | Own final freeze and migration notes. |

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
6. Hermes AI Agent and qwenpaw may inform tool-calling quality, function schema
   discipline, planner feedback loops, and MCP UX only where their public source
   or design details are available. Release-1.2.7 must not copy external code or
   depend on unavailable implementation details.
7. Release-2.0.0 entry is blocked unless release-1.2.7 has no remaining
   implementation-bearing HLD gap.

## 5. Workstreams

### WS-1 Multi-Board Acceptance Matrix

1. Define capability classes before concrete board families:
   - Extensible Unit;
   - Restricted Unit;
   - Relay-capable Unit;
   - Federated-access Unit;
   - storage-constrained Unit;
   - signing-capable or signing-required Unit.
2. Map representative board families and build presets into those classes while
   keeping shared Core/Unit contracts free of board-specific assumptions.
3. Record capability and artifact-admission evidence across representative
   classes rather than a single validation board.
4. Keep the matrix bounded and operator-runnable; do not require a full farm.
5. Add deterministic matrix rows first, then bounded real-board rows.

### WS-1A Restricted Unit Compatibility

1. Treat non-LLEXT or resource-limited targets as first-class compatibility
   outcomes rather than skipped hardware.
2. Define degraded deploy, update, event, query, and capability behavior for
   Restricted Units.
3. Ensure unsupported outcomes are explicit route, admission, or acceptance
   evidence instead of generic transport or build failures.

### WS-2 Resource Budget Governance

1. Turn heap, stack, app-slot, and staging budgets into governed release
   thresholds rather than best-effort evidence.
2. Record acceptance and rejection outcomes as explicit closure evidence.
3. Separate build-time candidate tuning from promoted runtime defaults.
4. Include transport-buffer and relay-buffer budget decisions where relevant.
5. Reject unsafe candidates before load or activation.

### WS-2A Agent Tool Skill MCP Excellence

1. Treat the release-1.2.6 Tool/Skill/MCP closure as the safety floor, not the
   product-quality ceiling.
2. Improve tool schema discipline, argument validation, and available-tool
   enforcement.
3. Keep Skill metadata, workflow catalog entries, and ground rules discoverable
   and drift-tested.
4. Expand governed MCP modes for read-only execution and approval-required
   proposals without bypassing Core policy.
5. Add planner repair feedback when provider plans choose invalid tools,
   violate Skill ground rules, or request forbidden MCP side effects.
6. Add Agent-assisted acceptance scenarios for discover, capability review,
   deploy-plan, artifact admission, activation approval, rollback review,
   federation route, relay fallback, compatibility rejection, and live event
   diagnosis.

### WS-3 Release And Rollback Hardening

1. Tighten release, activate, rollback, and cleanup runbooks.
2. Expand approval-visible rollback and lease-cleanup evidence.
3. Ensure release/rollback failure states produce explicit operator actions.

### WS-4 Signing And Provenance Enforcement

1. Strengthen signing/provenance expectations for promoted artifacts.
2. Keep compatibility rejection visible before load or activation.
3. Avoid claiming full production PKI if the project is not ready for it.
4. Record artifact identity, source manifest identity, build provenance, signing
   state, and per-target signing policy before admission.
5. Support explicit policy states: unsigned allowed, signature optional,
   signature required, and signature rejected.

### WS-5 Observability And Failure Diagnosis

1. Standardize bounded runtime observability for acceptance closure.
2. Improve operator-facing evidence for degraded, relay-failed, unreachable, and
   rollback-required states.
3. Keep all diagnostics structured and release-gate consumable.
4. Add closure-consumable evidence for stale route, compatibility rejection,
   signing rejection, and resource-budget rejection.
5. Preserve raw logs as supporting evidence, not the primary acceptance surface.

### WS-6 Acceptance Documentation And Runbooks

1. Finalize English and Chinese acceptance runbooks for setup, smoke,
   federation/relay fallback, hardware compatibility, and rollback handling.
2. Align README, release plans, progress ledger, AI Core LLD, and Unit LLD.
3. Prepare migration and operator handoff notes for 2.0.0.
4. Add operator-runnable Agent Tool/Skill/MCP-assisted acceptance flows.
5. Add real Core/Unit scenario execution and evidence collection procedures.

### WS-7 Final Regression And Closure Packaging

1. Re-run focused inherited regressions from 1.2.4, 1.2.5, and 1.2.6.
2. Materialize a final release-1.2.7 closure bundle with documentation,
   provider, multimodal, regression, hardware, route, Agent excellence,
   signing/provenance, observability, and real-scenario evidence.
3. Enter release-2.0.0 only when the remaining work is stabilization-only.

### WS-8 Real Core/Unit End-To-End Scenarios

Execution is anchored by
`docs/project/RELEASE_2.0.0_REAL_CORE_UNIT_SCENARIO_CHECKLIST.md`, which
defines the bounded scenario ids, shared preconditions, evidence bundle shape,
and the release-1.2.7 versus release-2.0.0 handoff boundary.

1. Define and implement deterministic neuro_core plus neuro_unit adapter E2E
   harnesses.
2. Run single Core plus single real Unit scene validation.
3. Run Core build/deploy/activate/rollback against a real Unit.
4. Run live Unit event ingestion and diagnosis scenarios.
5. Run multi-Core federation route and relay-assisted Unit access scenarios.
6. Run Agent Tool/Skill/MCP-assisted operation flows over the same scenario
   families.
7. Preserve a full real-scene rerun requirement for release-2.0.0 after freeze.
8. Keep the scenario ids and evidence artifact names stable between release-1.2.7
   closure and the release-2.0.0 frozen rerun.

## 6. Validation Gates

Release-1.2.7 cannot close until all gates pass:

1. Documentation and acceptance gate.
2. Multi-board hardware matrix gate.
3. Restricted Unit compatibility gate.
4. Resource budget governance gate.
5. Agent Tool/Skill/MCP excellence gate.
6. Release and rollback hardening gate.
7. Signing and provenance gate.
8. Observability and failure-diagnosis gate.
9. Real Core/Unit scenario gate.
10. Inherited regression gate.
11. Closure-summary gate.

## 7. Exit Criteria

Release-1.2.7 is complete when:

1. all remaining implementation-bearing HLD work is closed in release-1.2.7 or
   explicitly reclassified out of HLD-critical scope with a recorded decision;
2. the project has a bounded acceptance matrix across representative hardware
   and artifact classes;
3. Restricted Unit behavior is explicit and tested;
4. Agent Tool/Skill/MCP flows are product-grade, policy-governed, and audited;
5. release/rollback safety and acceptance runbooks are executable and audited;
6. real neuro_core plus neuro_unit scenario harnesses exist and representative
   real-scene rows pass;
7. closure-summary can report a clean release matrix for the 1.2.7 bundle;
8. release-2.0.0 can be treated as a stabilization, final-rerun, and promotion
   release.

## 8. Initial Implementation Order

1. Re-baseline this release plan, README, progress ledger, AI Core LLD, and Unit
   LLD around release-1.2.7 as the final implementation-heavy HLD closure line.
2. Add the HLD closure map and release-2.0.0 entry boundary.
3. Add deterministic capability-class and hardware acceptance matrix commands.
4. Add Restricted Unit compatibility outcomes.
5. Add resource-governance thresholds and rejection evidence.
6. Add Agent Tool/Skill/MCP excellence tests and planner repair evidence.
7. Harden release/rollback/cleanup/signing/provenance flows.
8. Add structured observability and failure diagnosis payloads.
9. Add real Core/Unit scenario harnesses and runbooks.
10. Expand closure-summary and produce a final release-1.2.7 bundle.

## 9. Initial Progress Estimate

1. Release-1.2.7 implementation progress after HLD completion re-baseline: about
   8%.
2. Release-1.2.7 closure progress: 0% until the new validation gates begin
   passing.
3. Overall HLD completion at release start: about 94%.
4. Overall HLD development completion target at release close: about 100% for
   non-stabilization implementation work.
5. Overall HLD completion target entering release-2.0.0 stabilization: about
   98% including remaining freeze, migration, final rerun, and promotion work.
