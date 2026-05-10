# Release 2.0.0 Pre-Promotion Real Core/Unit Scenario Checklist

## 1. Purpose

This checklist now serves as the active release-2.0.0 stabilization, freeze,
and promotion execution surface after release-1.2.7 closure. It is the single
bounded checklist for real neuro_core plus neuro_unit integration evidence that
must be rerun before release-2.0.0 promotion.

The machine-archivable JSON form is intentionally versioned and committed in
two repository files:

1. `docs/project/RELEASE_2.0.0_REAL_CORE_UNIT_SCENARIO_CHECKLIST.template.json`
   is the empty skeleton that matches the CLI-emitted template surface.
2. `docs/project/RELEASE_2.0.0_REAL_CORE_UNIT_SCENARIO_CHECKLIST.example.json`
   is a filled example showing how a rerun archive can record row status,
   evidence files, and blockers without inventing a different schema.

The checklist is intentionally scenario-oriented rather than board-oriented.
Every row must be satisfied through capability classes and governed evidence,
not through hardcoded dependence on the current lab board, router IP, Wi-Fi
setup, storage layout, or artifact staging path.

## 2. Promotion Boundary

Release-1.2.7 has now closed the implementation-bearing real-scene work:

1. scenario harnesses exist and are executable;
2. representative deterministic and bounded live rows pass;
3. independent closure payloads can be archived and consumed by
   `closure-summary`;
4. failure modes degrade into explicit compatibility, diagnosis, rollback, or
   operator-action evidence.

Release-2.0.0 now reruns and freezes the already-built surface:

1. rerun the approved checklist after contract freeze;
2. refresh evidence with the frozen release target and final artifact set;
3. confirm no scenario requires new implementation work;
4. treat failures as stabilization blockers, not scope expansion.

## 3. Shared Rules

Every scenario row must satisfy all of the following:

1. shared Core and Unit contracts remain hardware-agnostic;
2. artifact identity, provenance, and signing policy are recorded before live
   deploy or activate steps;
3. real-tool execution remains Core-governed, audit-visible, and lease-aware;
4. logs are supporting evidence only; closure consumes structured JSON payloads;
5. every failing row must emit explicit next actions for operator follow-up;
6. Restricted Unit behavior is an accepted compatibility outcome, not a skipped
   row;
7. release-2.0.0 reruns use the same scenario ids and expected evidence shapes.

## 4. Shared Preconditions

Complete these items before starting the scenario rows:

1. confirm the active release target, source manifest identity, and promoted
   artifact identity align;
2. confirm `hardware-acceptance-matrix`, `restricted-unit-compatibility`,
   `agent-excellence-smoke`, `signing-provenance-smoke`,
   `observability-diagnosis-smoke`, `release-rollback-hardening-smoke`, and
   `real-scene-e2e-smoke` commands are available on the target branch;
3. prepare one deterministic Core-only environment and one bounded real Unit
   environment;
4. confirm host-to-Unit connectivity, event transport reachability, and cleanup
   permissions;
5. create a fresh evidence directory under `smoke-evidence/` for the current
   closure or rerun session;
6. either generate a fresh checklist through
   `real-scene-checklist-template --release-target 2.0.0 --implementation-release 1.2.7`
   or copy the committed template/example JSON and replace the archive paths;
7. record the chosen capability class for each Unit target:
   - Extensible Unit
   - Restricted Unit
   - Relay-capable Unit
   - Federated-access Unit
   - storage-constrained Unit
   - signing-required Unit
8. predeclare the artifact set that will be used for live deployment and
   rollback.

## 5. Scenario Matrix

| Scenario id | Scenario family | Minimum objective | Required evidence artifacts | Primary gates |
| --- | --- | --- | --- | --- |
| RS-01 | Deterministic Core/Unit contract baseline | Prove the scenario harness, event semantics, and delegated tool path work without live hardware dependence. | no-model session evidence, `agent_excellence_result`, deterministic scenario run record | Agent excellence, regression |
| RS-02 | Single Core plus single real Unit live event continuity | Prove a live Unit event is ingested, delegated through Core reasoning, and reconciled by a real governed tool execution. | `live-event-smoke` payload, `real_scene_e2e_result` | Real Core/Unit scenario |
| RS-03 | Real Unit deploy, activate, query, rollback | Prove a real artifact can be admitted, activated, queried, and rolled back with explicit operator-visible outcomes. | artifact admission record, deploy or activate evidence, rollback evidence, session closure summary | Release and rollback, signing/provenance |
| RS-04 | Restricted Unit compatibility outcome | Prove a non-LLEXT or constrained target degrades with explicit compatibility evidence instead of generic failure. | `restricted_unit_compatibility` result, capability row evidence, operator next-action summary | Restricted Unit compatibility |
| RS-05 | Multi-Core federation route | Prove delegated Core routing still reaches Unit operations and preserves audit and event continuity. | federation or relay evidence, route summary, scenario run record | Federation, real Core/Unit scenario |
| RS-06 | Relay-assisted or degraded remote access | Prove relay fallback, unreachable detection, and route failure diagnosis produce explicit structured evidence. | relay failure closure, diagnosis payload, supporting transport evidence | Observability, release safety |
| RS-07 | Agent-assisted governed operation flow | Prove discover, capability review, deploy-plan, approval-visible action, and diagnosis all stay within Tool/Skill/MCP governance. | `agent_excellence_result`, session evidence, approval or policy evidence | Agent excellence, documentation |
| RS-08 | Cleanup and rerun readiness | Prove leases, staging artifacts, and runtime state can be returned to a clean rerunnable baseline. | cleanup evidence, lease query evidence, final checklist review | Release and rollback, closure-summary |

## 6. Per-Scenario Exit Checks

A scenario row counts as passed only when all row-specific checks are true.

### RS-01 Deterministic Core/Unit Contract Baseline

1. delegated reasoning selects only governed tools;
2. selected tool contracts satisfy Skill and workflow catalog rules;
3. deterministic evidence shape matches the live row schema family;
4. no board-specific assumptions appear in shared contracts.

### RS-02 Single Core Plus Single Real Unit Live Event Continuity

1. a live Unit event is collected and persisted;
2. event source remains consistent across ingest, execution evidence, and
   agent-run evidence;
3. real tool adapter presence is explicit;
4. real governed tool execution succeeds;
5. `system_state_sync` or the approved equivalent reconciliation tool is
   recorded.

### RS-03 Real Unit Deploy, Activate, Query, Rollback

1. artifact identity and provenance are recorded before admission;
2. admission, activation, and query states are explicit;
3. rollback path is executable and audited;
4. failure states produce operator next actions rather than silent cleanup.

### RS-04 Restricted Unit Compatibility Outcome

1. capability limits are explicit;
2. unsupported LLEXT or resource-heavy paths fail closed as compatibility
   outcomes;
3. operator guidance identifies the accepted degraded mode.

### RS-05 Multi-Core Federation Route

1. delegated Core routing is explicit and auditable;
2. Unit-side event continuity remains attributable to the correct Core and
   route;
3. route degradation does not collapse into transport-only ambiguity.

### RS-06 Relay-Assisted Or Degraded Remote Access

1. stale route, unreachable target, and relay failure are distinguishable;
2. diagnosis payloads expose operator next actions;
3. fallback handling does not bypass approval, audit, or cleanup boundaries.

### RS-07 Agent-Assisted Governed Operation Flow

1. Tool, Skill, and MCP descriptors remain discoverable and drift-free;
2. invalid tool or MCP plans fail before adapter execution;
3. governed read-only execution and approval-required proposal paths remain
   distinct.

### RS-08 Cleanup And Rerun Readiness

1. no stale leases remain;
2. runtime cleanup is explicit;
3. the evidence bundle is sufficient for a same-day rerun without hidden manual
   state.

## 7. Evidence Bundle Layout

Archive the checklist run with a bounded, reviewable layout:

1. `closure.db` or equivalent session store;
2. `hardware-acceptance-matrix.json`;
3. `restricted-unit-compatibility.json`;
4. `agent-excellence-smoke.json`;
5. `signing-provenance-smoke.json`;
6. `live-event-smoke.json`;
7. `real-scene-e2e-smoke.json`;
8. relay or diagnosis JSON when RS-05 or RS-06 is exercised;
9. `closure-summary.json`;
10. a short operator decision note naming passed rows, failed rows, deferred rows,
    and rerun blockers.

## 8. Release-1.2.7 Exit And Release-2.0.0 Entry

Release-1.2.7 should not claim WS-8 closure until:

1. RS-01 through RS-04 pass on at least one representative bounded path;
2. at least one of RS-05 or RS-06 passes with structured diagnosis evidence;
3. RS-07 passes with governed Tool/Skill/MCP evidence;
4. RS-08 proves rerun cleanliness;
5. `closure-summary` reports the real-scene gate green when the archived
   `real-scene-e2e-smoke` payload is supplied.

Release-2.0.0 entry is allowed only when the remaining checklist work is:

1. frozen-contract rerun;
2. compatibility refresh;
3. migration or operator handoff note refresh;
4. promotion approval.

If any scenario still needs new harness logic, new evidence schema, or new
shared contract semantics, that work belongs back in release-1.2.7 rather than
release-2.0.0.
