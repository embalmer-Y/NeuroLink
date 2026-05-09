# Release 1.2.4 Core Orchestrator And Production Live Service Plan

## 1. Overview

Release 1.2.4 advances NeuroLink from the closed release-1.2.3 autonomous
perception baseline into the next HLD-critical milestone: Core-owned Unit App
build/deploy orchestration plus a production-shaped live event service.

Release-1.2.3 proved bounded event ingestion, deterministic daemon replay,
operational topic promotion, approval-bounded recovery evidence, and real
hardware callback/state/update-plane closure. Release-1.2.4 uses that
foundation to close the largest remaining Phase 1 HLD gap: AI Core must be able
to plan, build, validate, deploy, activate, observe, and recover Unit Apps as a
first-class Core workflow rather than relying on loosely coordinated operator
scripts.

This release intentionally does not attempt full Core federation or the full
local multimodal vLLM profile matrix yet. It creates the production
orchestration spine those later releases need.

## 2. Four-Release Roadmap To 2.0.0

The current overall HLD completion estimate after release-1.2.3 is about 64%.
The project goal is to close the remaining HLD surface across four minor
releases, then promote to release-2.0.0.

1. `release-1.2.4`: Core App Build/Deploy Orchestrator and production live
   event service.
   - Target HLD completion: about 74%.
   - Main outcome: Core owns the app artifact lifecycle and long-running event
     ingestion evidence instead of depending on manual script choreography.
2. `release-1.2.5`: local multimodal Affective runtime, inference profile
   routing, and memory governance hardening.
   - Target HLD completion: about 82%.
   - Main outcome: the HLD multimodal/vLLM decision becomes executable through
     profile routing, health probes, fallback, and memory retention policy.
3. `release-1.2.6`: Core-to-Core federation and Gateway Unit relay baseline.
   - Target HLD completion: about 91%.
   - Main outcome: topology sync, delegated execution contracts, relay-visible
     Unit attachment, and minimum trust metadata are proven in deterministic and
     bounded live form.
4. `release-1.2.7`: productization hardening and release-2.0.0 readiness.
   - Target HLD completion: about 97%.
   - Main outcome: multi-board build/deploy matrix, resource budget governance,
     release/rollback policy hardening, observability, operator runbooks, and
     full regression/hardware evidence are ready for 2.0.0 promotion.

Release-2.0.0 should be a stabilization, compatibility, and acceptance release,
not a large feature release. Its scope should be final docs, migration notes,
API/contract freeze, full hardware evidence rerun, and version promotion.

## 2.1 Current Implementation Status (2026-05-09)

Release-1.2.4 is closed. The following Core orchestration surfaces now make up
the completed release baseline:

1. `app-build-plan`
   - canonical Unit App build metadata, target resolution, and artifact-path
     planning are in place as structured Core output.
2. `app-artifact-admission`
   - source identity, ELF identity, target architecture, size/hash evidence,
     and admission decisions are explicit and persisted.
3. `app-deploy-plan`
   - the protected preflight -> lease -> prepare -> verify -> approval ->
     activate -> cleanup sequence is fixed as structured Core output, and the
     generated command templates now use the active interpreter path instead of
     assuming a host `python` alias.
4. `app-deploy-prepare-verify`
   - the executable deploy slice now passes through the real Neuro CLI adapter
     on hardware for preflight, activate-lease acquire, deploy prepare, deploy
     verify, lease release, and final lease cleanup.
   - the closure parser now tolerates setup/log-prefixed JSON output from the
     preflight script, which was the real hardware defect exposed during the
     final release gate.
5. `app-deploy-activate`
   - approval-bounded activation is executable as an explicit Core slice and
     records activation-health evidence plus guarded rollback candidates when
     activation health reports `rollback_required`.
6. `app-deploy-rollback`
   - rollback is approval-bounded, resumable, fail-closed on residual running
     app or held rollback lease, exposes explicit `pending_approval` / `denied`
     / `expired` operator outcomes, emits structured failure summaries for
     transport and lease-owner failures, and surfaces missing rollback lease as
     explicit `lease_not_found`.
7. release-gate evidence persistence
   - `app-deploy-activate` and `app-deploy-rollback` persist decision and
     execution evidence into `CoreDataStore` through the existing optional
     SQLite-backed release-gate records.
8. `event-service`
   - the bounded supervised live-event service now records `start`, `ready`,
     `heartbeat`, `events_persisted`, `restart`, `stale_endpoint`, `no_events`,
     `no_reply`, and `clean_shutdown` lifecycle facts.
   - restart-safe checkpoint and dedupe continuity now reuse the existing
     router/datastore evidence surfaces instead of introducing a parallel schema.
9. operator and hardware closure
   - the English and Chinese runbooks plus README now describe the Core-owned
     build/admit/deploy/event-service operator path and its fallback script
     diagnostics.
   - on the connected DNESP32S3B path, `app-build-plan ->
     app-artifact-admission -> app-deploy-prepare-verify` completed with final
     clean leases, closing the real hardware gate for this release.

The remaining HLD work is no longer release-1.2.4 debt. It is assigned to the
planned 1.2.5 through 1.2.7 burn-down and the eventual 2.0.0 stabilization
release.

## 3. Fixed Decisions

1. Release 1.2.4 keeps release-1.2.3 as the frozen event-ingest and recovery
   baseline.
2. Core build/deploy orchestration must reuse existing Neuro CLI, build scripts,
   preflight scripts, lease surfaces, approval gates, and artifact validation
   rather than inventing a parallel control plane.
3. App build output must be treated as untrusted until Core records manifest,
   target, ELF, ABI/version, size, and optional signature/admission evidence.
4. Deploy, activate, rollback, and cleanup remain lease-aware and approval-aware.
   The Core may prepare evidence automatically, but side-effecting release gates
   must stay policy-governed.
5. Production live event ingestion must preserve the release-1.2.3 fail-closed
   behavior. Empty subscriptions, parser failures, and no-reply transport states
   must remain explicit failures rather than synthetic green runs.
6. The first production service shape can remain a single-process Core CLI or
   daemon entrypoint, but module boundaries must align with the AI Core LLD so
   later service splitting is mechanical.

## 4. Target Architecture Slice

The release-1.2.4 slice consists of:

1. `neurolink_core.orchestrator` or equivalent workflow-owned helpers
   - target profile resolution, build plan creation, artifact admission,
     deploy plan creation, activation health observation, and rollback evidence.
2. `neurolink_core.workflow`
   - Core workflow entrypoints for build/deploy orchestration, approval-gated
     activation, recovery, and live event service supervision.
3. `neurolink_core.tools`
   - bounded tool contracts for build, artifact inspect, preflight, deploy
     prepare/verify/activate, rollback, cleanup, and live event service status.
4. `neurolink_core.data`
   - persisted artifact, deployment, admission, live-service heartbeat, and
     recovery facts.
5. `neurolink_core.events`
   - long-running live subscriber continuity, checkpointed dedupe state, and
     service health event normalization.
6. `neurolink_core.cli`
   - operator entrypoints for `app-build-plan`, `app-deploy-plan`,
     `app-release-gate`, and `event-service` style workflows.
7. existing scripts and Neuro CLI
   - `build_neurolink.sh`, `preflight_neurolink_linux.sh`,
     `smoke_neurolink_linux.sh`, `neuro_cli.py deploy ...`, and
     `run_unit_live_event_probe.sh` remain canonical lower-level adapters.

## 5. Workstreams

### WS-1 HLD Gap Closure Map And 2.0.0 Burn-Down

1. Add a table-based HLD gap map covering:
   - Core App build/deploy orchestration.
   - production live event service.
   - local multimodal inference profile routing.
   - Core federation.
   - Gateway Unit relay.
   - multi-board build matrix.
   - release/rollback/resource governance.
2. Assign each remaining HLD gap to release-1.2.4, 1.2.5, 1.2.6, 1.2.7, or
   release-2.0.0 acceptance.
3. Record progress estimates separately for release scope and total HLD scope.

### WS-2 Core App Build Plan

1. Add a Core build-plan contract for Unit Apps.
2. Resolve target board, app id, source project, build preset, architecture,
   expected artifact path, and output manifest.
3. Reuse existing build scripts through bounded Core tool adapters.
4. Persist build plan, command evidence, artifact path, artifact size, build id,
   manifest version, and target compatibility metadata.
5. Fail closed when build output is missing, stale, non-ELF, malformed, or does
   not match the requested app identity.

### WS-3 Artifact Admission And Release Metadata

1. Promote artifact inspection from script-level checks into Core evidence.
2. Validate ELF identity beyond the first magic bytes, app identity string,
   manifest semantic version, target architecture, and size bounds.
3. Add a release metadata schema for build id, source path, target board,
   artifact hash, manifest version, and admission result.
4. Leave cryptographic signing as an explicit follow-up if the current Unit path
   lacks a complete signing verifier, but preserve the schema fields now.

### WS-4 Core Deploy Plan And Approval-Gated Activation

1. Add a deploy-plan workflow that sequences preflight, lease acquisition,
   prepare, verify, activation approval, activate, activation health guard, and
   lease cleanup.
2. Keep prepare/verify automatable when policy permits, but require explicit
   approval for activation in release-gate mode.
3. Persist deploy plan, update lease evidence, prepare/verify replies,
   activation decision, activation health observation, and final app state.
4. Ensure every reply payload `status` is checked, not only transport success.
5. Preserve cleanup behavior when any step fails.

### WS-5 Guarded Recovery And Rollback Integration

1. Reuse the release-1.2.3 `activation_health_observation`,
   `recovery_candidate`, and `system_rollback_app` surfaces.
2. When activation health is `rollback_required`, produce a pending rollback
   approval with target app, rollback lease, reason, and artifact provenance.
3. Add deterministic tests for approve, deny, expire, missing lease, lease holder
   mismatch, and no-reply rollback cases.
4. Add bounded hardware evidence for one successful deploy recovery or one
   deterministic simulated recovery when hardware cannot be safely induced.

### WS-6 Production Live Event Service

1. Promote bounded `live-event-smoke` concepts into a supervised live event
   service command.
2. Support app-event and generic Unit event subscriptions using the existing
   `monitor app-events` and `monitor events` adapters.
3. Persist service lifecycle facts: start, ready, heartbeat, events persisted,
   restart, stale endpoint, no events, no reply, and clean shutdown.
4. Store subscriber checkpoints and dedupe state so service restart does not
   retrigger already persisted events.
5. Add a bounded runtime mode for tests and release evidence so CI and operator
   smoke remain deterministic.

### WS-7 Operator Runbook And Script Alignment

1. Update English and Chinese AI Core runbooks with Core-owned app build/deploy
   and event-service flows.
2. Keep the existing script-level flows as lower-level troubleshooting paths.
3. Add clear guidance for endpoint drift, stale artifacts, lease holder mismatch,
   serial visibility, and no-reply states.
4. Update README release notes to identify release-1.2.4 as the active plan.

## 6. Validation Gates

All release-1.2.4 validation gates are green:

1. HLD gap map gate
    - remaining HLD items are assigned to 1.2.5, 1.2.6, 1.2.7, or 2.0.0 rather
       than left as release-1.2.4 ambiguity.
2. Build-plan gate
    - Core produces canonical build metadata and the real hardware closure path
       reported `build/neurolink_unit_app/neuro_unit_app.llext` for
       `app-build-plan --app-id neuro_unit_app`.
3. Artifact admission gate
    - admitted artifacts carry source identity, target, ELF metadata, size, and
       SHA256 evidence; the final closure admission reported `machine_name=xtensa`
       and recorded the artifact hash.
4. Deploy-plan gate
    - Core executes prepare/verify through the real Neuro CLI adapter, inspects
       nested payload statuses, parses log-prefixed preflight JSON safely, and
       uses interpreter-stable command templates.
5. Activation approval gate
    - activation remains approval-bounded in release mode and records guarded
       rollback candidates instead of auto-applying rollback.
6. Recovery gate
    - rollback-required activation health creates pending rollback approval,
       explicit operator outcomes, missing-lease semantics, and structured
       failure/cleanup evidence without uncontrolled side effects.
7. Event-service gate
    - the live event service records heartbeat, restart, event, checkpoint,
       stale-endpoint, and shutdown evidence with restart-safe dedupe continuity
       and fail-closed empty/unreachable source handling.
8. Real hardware gate
    - on the connected DNESP32S3B path, the Core-owned
       `app-build-plan -> app-artifact-admission -> app-deploy-prepare-verify`
       flow completed with successful cleanup and final empty leases.
9. Regression gate
    - focused Core regressions for `event_service`, `app_deploy_plan`, and
       `app_deploy_prepare_verify` passed during closure, and release-target
       regressions keep the promoted CLI/sample-app identity aligned.

## 7. Acceptance Criteria

Release-1.2.4 is complete and closed. The release satisfies the acceptance
criteria as follows:

1. Core owns a documented app build/deploy workflow with persisted evidence.
2. Artifact admission is explicit and rejects missing, stale, placeholder, and
   malformed artifact cases.
3. Prepare/verify/activate/recovery flows reuse the protected Neuro CLI update
   plane and inspect nested reply payload statuses rather than transport success
   alone.
4. Activation and rollback remain approval-bounded in release-gate mode.
5. A supervised live event service exists with restart-safe dedupe, checkpoint,
   heartbeat, restart, and stale-endpoint evidence.
6. English and Chinese runbooks describe the operator path and fallback script
   diagnostics for release-1.2.4 operations.
7. The release records total HLD completion movement from about 64% to about
   75%, with the remaining work assigned to 1.2.5 through 2.0.0.

## 8. Initial Implementation Order

1. Add the HLD gap map and release burn-down table.
2. Add build-plan and artifact-admission data schemas and focused unit tests.
3. Wrap existing build and artifact inspection scripts as Core tool contracts.
4. Add deploy-plan workflow over preflight, prepare, verify, activation approval,
   activation health, and cleanup.
5. Add event-service bounded runtime and checkpoint persistence.
6. Update runbooks and README.
7. Run focused tests, adjacent Neuro CLI and Core regression, script checks, and
   one bounded hardware closure pass.

## 9. Out Of Scope For Release 1.2.4

1. Full Core-to-Core federation implementation.
2. Gateway Unit relay as a production path.
3. Complete local vLLM multimodal model matrix.
4. Full cryptographic app signing enforcement if Unit-side verifier support is
   not ready in the current runtime.
5. Multi-board hardware matrix closure beyond the connected DNESP32S3B path.
6. Release-2.0.0 API freeze.

## 10. Final Progress Estimate

1. Release-1.2.4 implementation progress: 100%.
2. Release-1.2.4 closure progress: 100%.
3. Overall HLD completion at release start: about 64%.
4. Overall HLD completion at release close: about 75%.

## 11. Closure Result

Release-1.2.4 is closed against the current Linux operator host and connected
DNESP32S3B evidence set.

Final closure evidence includes:

1. focused Core event-service regressions for heartbeat, restart continuity,
   and stale-endpoint handling;
2. focused Neuro CLI release-target regressions (`5 passed, 122 deselected`) so
   capabilities, workflow text, and sample-app source identity remain aligned
   with the promoted release marker;
3. focused Core deploy-plan and prepare/verify regressions for noisy preflight
   JSON parsing and interpreter-stable command templates;
4. direct Neuro CLI capabilities JSON reporting `release_target = "1.2.4"`;
5. rebuilt `neuro_unit_app.llext` containing
   `neuro_unit_app-1.2.4-cbor-v2`;
6. serial-required real hardware preflight with `status=ready` after endpoint
   correction;
7. real `app-build-plan --app-id neuro_unit_app` reporting the canonical Unit
   App artifact path;
8. real `app-artifact-admission --app-id neuro_unit_app` recording admitted ELF
   metadata and artifact hash for `build/neurolink_unit_app/neuro_unit_app.llext`;
9. real `app-deploy-prepare-verify --app-id neuro_unit_app --node unit-01`
   succeeding through `deploy_verify` with cleanup attempted and final
   `query_leases=[]`;
10. CRLF-aware `git diff --check` across the NeuroLink repository;
11. canonical host release identity promoted to `RELEASE_TARGET = "1.2.4"`.

Deferred follow-ups remain outside the release gate: local multimodal runtime
profile routing, memory-governance hardening, broader hardware matrix coverage,
Core federation, Gateway relay, and the eventual release-2.0.0 stabilization
work.
