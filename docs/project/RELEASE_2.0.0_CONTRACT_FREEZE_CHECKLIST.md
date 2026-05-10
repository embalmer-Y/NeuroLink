# Release 2.0.0 Contract Freeze Checklist

## 1. Purpose

This checklist freezes the public contracts that must remain stable while the
project completes the release-2.0.0 final rerun and promotion. It is the first
execution step after creating the release-2.0.0 finalization plan.

The release identity was intentionally kept at `1.2.7` until a fresh 2.0.0
promotion bundle was green. This checklist froze the behavior that release
2.0.0 had to prove before promotion.

## 2. Freeze Decision

Status: `promoted_after_green_bundle`

Date: 2026-05-10

Decision owner: release operator with GitHub Copilot evidence preparation

Allowed change class before promotion:

1. documentation corrections;
2. evidence wiring fixes that preserve existing schemas;
3. stabilization fixes for already-claimed 1.2.7 behavior;
4. environment recovery notes for hardware reruns;
5. release identity promotion after all gates are green.

Blocked change class before promotion:

1. new Agent capability families;
2. new Unit command planes;
3. incompatible closure-summary schema changes;
4. hardware-specific assumptions embedded into shared Core or Unit contracts;
5. direct model/tool execution paths that bypass Core policy.

## 3. Frozen Surfaces

### FS-01 AI Core CLI Evidence Surface

Frozen commands:

1. `no-model-dry-run`
2. `event-replay`
3. `event-daemon`
4. `live-event-smoke`
5. `event-service`
6. `activation-health-guard`
7. `app-build-plan`
8. `app-artifact-admission`
9. `hardware-compatibility-smoke`
10. `hardware-acceptance-matrix`
11. `resource-budget-governance-smoke`
12. `signing-provenance-smoke`
13. `app-deploy-plan`
14. `app-deploy-prepare-verify`
15. `app-deploy-activate`
16. `app-deploy-rollback`
17. `agent-run`
18. `tool-manifest`
19. `skill-descriptor`
20. `mcp-descriptor`
21. `agent-excellence-smoke`
22. `observability-diagnosis-smoke`
23. `release-rollback-hardening-smoke`
24. `real-scene-checklist-template`
25. `real-scene-e2e-smoke`
26. `session-inspect`
27. `closure-summary`
28. `approval-inspect`
29. `approval-decision`
30. `maf-provider-smoke`
31. `multimodal-profile-smoke`
32. `federation-route-smoke`

Freeze rule: command names, output `status` semantics, JSON mode, and release
evidence payload purpose are frozen. Stabilization may add optional fields but
must not remove existing fields consumed by `closure-summary` or runbooks.

### FS-02 Closure And Evidence Schemas

Frozen schema versions:

1. `1.2.7-closure-summary-v13`
2. `1.2.5-documentation-closure-v1`
3. `1.2.6-regression-closure-v2`
4. `1.2.6-relay-failure-closure-v1`
5. `1.2.6-hardware-compatibility-closure-v1`
6. `1.2.7-hardware-acceptance-matrix-v1`
7. `1.2.7-agent-excellence-smoke-v1`
8. `1.2.7-signing-provenance-smoke-v1`
9. `1.2.7-real-scene-e2e-smoke-v1`
10. `1.2.7-observability-diagnosis-smoke-v1`
11. `1.2.7-release-rollback-hardening-smoke-v1`
12. `1.2.7-resource-budget-governance-smoke-v1`
13. `2.0.0-real-scene-checklist-template-v1`

Freeze rule: final release-2.0.0 promotion may consume these schema versions.
The `2.0.0` release name is a promotion target, not a requirement to rename all
stable 1.2.x evidence contracts before promotion.

### FS-03 Validation Gate Matrix

Frozen final gate expectation:

1. `validation_gate_summary.ok=true`
2. `validation_gate_summary.passed_count=20`
3. `validation_gate_summary.failed_gate_ids=[]`
4. `validation_gates.closure_summary_gate=true`

Freeze rule: gate ids may be documented and rerun, but not weakened. Any gate
that fails in the release-2.0.0 bundle must be closed, explicitly deferred by
approval, or classified as an environment blocker with evidence.

### FS-04 Neuro CLI Release Identity And JSON Semantics

Current implementation identity: `RELEASE_TARGET = "2.0.0"`

Promotion target: `2.0.0`

Frozen behavior:

1. JSON replies must carry command-level `status` that callers inspect;
2. transport-level success is not enough to treat a command as successful;
3. `system capabilities` remains the canonical capability and release identity
   inspection surface;
4. workflow catalog release identity must promote together with Neuro CLI;
5. release identity promotion occurred only after the fresh 2.0.0 bundle was green.

### FS-05 Unit Topic And Operation Contracts

Frozen Unit planes:

1. `neuro/<node-id>/cmd/lease/acquire`
2. `neuro/<node-id>/cmd/lease/release`
3. `neuro/<node-id>/cmd/app/<app-id>/<command-name>`
4. `neuro/<node-id>/cmd/app/<app-id>/start`
5. `neuro/<node-id>/cmd/app/<app-id>/stop`
6. `neuro/<node-id>/query/device`
7. `neuro/<node-id>/query/apps`
8. `neuro/<node-id>/query/leases`
9. `neuro/<node-id>/event/state`
10. `neuro/<node-id>/event/update`
11. `neuro/<node-id>/event/lease/<lease-id>`
12. `neuro/<node-id>/update/app/<app-id>/prepare`
13. `neuro/<node-id>/update/app/<app-id>/verify`
14. `neuro/<node-id>/update/app/<app-id>/activate`
15. `neuro/<node-id>/update/app/<app-id>/rollback`

Freeze rule: shared Unit contracts remain hardware-agnostic. Board-specific
serial, Wi-Fi, memory, endpoint, or driver recovery details belong in runbooks
and evidence, not in generic Core/Unit behavior.

### FS-06 AI Safety And Tool Governance

Frozen policy:

1. models propose decisions or plans only;
2. Core validates tool availability, arguments, lease ownership, approvals,
   Skill rules, MCP mode, and side-effect class;
3. side-effecting operations require approval evidence;
4. Rational backends cannot execute shell, Neuro CLI, MCP, or Unit tools
   directly;
5. provider model calls are explicit opt-in;
6. missing provider requirements fail closed with structured metadata.

### FS-07 Memory And Multimodal Contracts

Frozen behavior:

1. deterministic local memory evidence remains valid for release closure;
2. Mem0-backed memory remains opt-in and environment-driven;
3. memory governance and recall gates remain part of `closure-summary`;
4. multimodal profile smoke records input modes, route decision, profile
   readiness, and no-model-call behavior unless explicitly requested.

### FS-08 Hardware Compatibility Classes

Frozen compatibility classes:

1. Extensible Unit;
2. Restricted Unit;
3. Relay-capable Unit;
4. Federated-access Unit;
5. Storage-constrained Unit;
6. Signing-required Unit.

Freeze rule: release-2.0.0 must stay capability-driven. Do not encode the
DNESP32S3B test board as the only accepted hardware shape.

### FS-09 Release Evidence Bundle Shape

Frozen bundle root:

```text
smoke-evidence/release-2.0.0-promotion-<UTC>/
```

Required final artifacts:

1. `closure.db`
2. `real-scene-checklist.json`
3. `documentation-closure.json`
4. `provider-smoke.json`
5. `multimodal-profile-smoke.json`
6. `regression-closure.json`
7. `hardware-compatibility.json`
8. `hardware-acceptance-matrix.json`
9. `resource-budget-governance-smoke.json`
10. `agent-excellence-smoke.json`
11. `signing-provenance-smoke.json`
12. `observability-diagnosis-smoke.json`
13. `release-rollback-hardening-smoke.json`
14. `live-event-smoke.json`
15. `real-scene-e2e-smoke.json`
16. `closure-summary-final.json`
17. promotion checklist and approval JSON

### FS-10 Promotion Identity Boundary

Promotion is frozen as the last step after evidence, not the first step.

Promotion touches:

1. Neuro CLI `RELEASE_TARGET`;
2. workflow catalog release identity;
3. sample Unit app source identity;
4. sample Unit app manifest/build identity;
5. tests that assert release identity;
6. rebuilt Unit app artifact;
7. final evidence after promotion.

## 4. Open Items Before Rerun

1. Archive this checklist in JSON form.
2. Generate a fresh `release-2.0.0-promotion-*` evidence directory.
3. Run deterministic Core evidence into the promotion bundle.
4. Run hardware preflight and bounded live rows when the board is ready.
5. Build final `closure-summary-final.json`.
6. Promote identity only after the final bundle is green.

## 5. Checklist Result

Result: `ready_for_fresh_promotion_bundle`

Rationale: no implementation-bearing contract gaps are identified at this
stage. Remaining work is rerun, evidence capture, blocker classification, and
final identity promotion after green gates.
