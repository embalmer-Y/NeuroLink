# Release 1.2.3 Autonomous Perception Plan

## 1. Overview

Release 1.2.3 advances NeuroLink from the closed release-1.2.2 real-LLM Core
baseline into the next HLD-critical milestone: persistent perception,
event-driven Core behavior, and production-shaped recovery evidence.

This release does not start broad multi-Core federation, provider-matrix
expansion, or dynamic app build/deploy orchestration yet. It focuses on the
shared infrastructure those later slices depend on: event ingestion, perception
frames, event-triggered Affective wake-up, deterministic daemon replay,
notification evidence, restart-safe dedupe behavior, and approval-bounded
recovery evidence after activation failure.

## 2. Fixed Decisions

1. Release 1.2.3 keeps release-1.2.2 as the frozen real-provider baseline and
   builds the next slice primarily in deterministic and replayable form first.
2. Event facts must persist before reasoning. Replay and daemon-style flows must
   not invent a separate execution path that bypasses the existing workflow,
   policy, memory, audit, or tool-adapter boundaries.
3. Event-triggered Affective wake remains the only user-facing presentation path.
   Rational planning remains internal plan evidence and tool-selection logic.
4. Release 1.2.3 daemon behavior is initially delivered as deterministic replay
   and file-backed continuity before a live long-running subscriber is promoted
   to closure-gate status.
5. Restart continuity must avoid duplicate salience triggers by seeding the
   event router from previously persisted dedupe keys.

## 3. Target Architecture Slice

The release-1.2.3 perception slice consists of:

1. `neurolink_core.events`
   - event normalization, dedupe, subscriber fanout, and router seeding.
2. `neurolink_core.data`
   - persisted events, frames, notification facts, and dedupe-key recovery.
3. `neurolink_core.workflow`
   - deterministic event replay, daemon-style multi-cycle replay, event-driven
     salience policy, notification evidence, and restart-safe dedupe behavior.
4. `neurolink_core.cli`
   - `event-replay` and `event-daemon` replay entrypoints.
5. `neurolink_core.agents`
   - operational event wake policy for endpoint drift, degraded health,
     activation failure, and offline/online state transitions.

## 4. Workstreams

### WS-1 Event Replay And Perception Spine

1. Add deterministic `event-replay` execution over existing workflow contracts.
2. Record replay summaries: provided events, normalized events, duplicates, and
   observed topics.
3. Preserve the same persistence, memory candidate, policy, tool, and audit path
   used by `agent-run` and `no-model-dry-run`.

### WS-2 Daemon-Style Replay And Restart Continuity

1. Add deterministic `event-daemon` replay over ordered event batches.
2. Share a router across cycles so dedupe persists during one daemon lifetime.
3. Seed the router from persisted dedupe keys so restarts do not retrigger the
   same event facts.

### WS-3 Event-Triggered Affective Notification Evidence

1. Promote `notification_dispatch` from a workflow step name into structured
   evidence.
2. Persist a `notification_dispatch` fact per execution span.
3. Add notification summary metadata to audit records.
4. Distinguish `interactive_response`, `event_driven_notification`, and
   `observation_only` delivery kinds.

### WS-4 Operational Salience Policy

1. Treat the following semantic topics as explicit Affective wake signals even
   when raw priority is low:
   - `unit.network.endpoint_drift`
   - `unit.health.degraded`
   - `unit.lifecycle.activate_failed`
   - `unit.state.offline`
   - `unit.state.online`
2. Keep tool execution read-only in this deterministic slice unless later policy
   explicitly opens a guarded recovery path.

### WS-5 Activation Health And Guarded Recovery Evidence

1. Route `unit.lifecycle.activate_failed` into a dedicated read-only activation
   health observer.
2. Persist `activation_health_observation` and `recovery_candidate` facts so
   operator review does not depend on raw audit scanning.
3. Keep rollback behind explicit approval while surfacing rollback lease
   ownership and target app evidence.
4. Expose the recovery summary through approval inspection and runbook-ready
   operator commands.

## 5. Validation Gates

1. Event replay gate
   - replay fixtures execute through the standard workflow and persist events,
     facts, tool results, audit rows, and replay summaries.
2. Daemon replay gate
   - multi-batch replay preserves dedupe across cycles and across DB-backed
     restart.
3. Notification evidence gate
   - each event-triggered execution records a `notification_dispatch` fact and
     `notification_summary` audit payload.
4. Operational wake gate
   - low-priority endpoint drift and other operational topics still trigger a
     Rational window and event-driven notification evidence.
5. Activation recovery gate
    - activate-failed replay produces activation health summary,
       `activation_health_observation`, `recovery_candidate`, and a pending
       approval-bounded rollback request when rollback is required.
6. Bounded live ingest gate
   - a real `monitor app-events` subscription can be ingested through the Core
     workflow path and preserves `neuro_cli_app_events_live` provenance plus
     real-adapter evidence.
7. Regression gate
   - focused Core replay/event tests stay green while deterministic baselines
     remain intact.

## 6. Current Implementation Status

The following release-1.2.3 slices are already implemented in the current
working tree:

1. `event-replay` CLI and workflow helper.
2. `event-daemon` deterministic replay CLI and workflow helper.
3. shared-router cross-batch dedupe.
4. DB-seeded dedupe continuity for daemon restart.
5. structured `notification_dispatch` facts and `notification_summary` audit
   payloads.
6. operational salience wake policy for endpoint drift and related topics.
7. `activation-health-guard` CLI and `system_activation_health_guard` tool
   contract.
8. persisted `activation_health_observation` facts for post-activation review.
9. `recovery_candidate` facts, `recovery_candidate_summary` audit payloads, and
   pending `system_rollback_app` approval requests for rollback-required health
   results.
10. operator-facing approval context that surfaces rollback evidence for
    `approval-inspect` and `approval-decision`.
11. one-shot Neuro CLI agent-event ingestion now preserves explicit provenance as
   `neuro_cli_agent_events` in workflow execution evidence and `agent_run_evidence`.
12. bounded Core `live-event-smoke` over real Neuro CLI `monitor app-events`
   with persisted `neuro_cli_app_events_live` provenance.
13. bounded Core `live-event-smoke --event-source unit` over real Neuro CLI
    `monitor events` with persisted `neuro_cli_events_live` provenance.
14. shared live-event normalization that promotes raw Unit `callback_event`,
    `lease_event`, `state_event`, and `update_event` payloads into operational
    topics such as `unit.callback`, `unit.state.online`, and
    `unit.lifecycle.activate_failed`.
15. real hardware proof that a raw Unit framework `state_event` reaches Core
    through `event/**` and lands as `unit.state.online`.
16. a repeatable `run_unit_live_event_probe.sh` helper that coordinates the
    ready-file listener handshake with callback, state-online, or
    update-activate trigger sequences for release closure evidence.
17. real hardware proof that a generic Unit listener can ingest bounded
    update-plane traffic from a coordinated `prepare -> verify -> activate`
    sequence and promote it into Core lifecycle topics.
18. serial Zenoh endpoint recovery now tolerates successful shell output even
    when trailing warning text would otherwise trip the generic `shell_error`
    classifier.

## 7. Closure Decision

Release-1.2.3 is now treated as closed for the current HLD slice.

1. The real generic Unit live-ingest path is proven on hardware for callback,
   lease, `state_event -> unit.state.online`, and update-plane recovery traffic.
2. Raw Unit `state_event` and `update_event` payloads already have deterministic
   semantic promotion coverage for degraded, offline, endpoint-drift, and
   activate-failed topics.
3. The final adjacent Neuro CLI/Core regression surface is green after the last
   parser hardening and hardware closure run.
4. Additional real hardware capture for `unit.lifecycle.activate_failed`,
   degraded, offline, or endpoint-drift remains useful follow-up evidence, but
   it is no longer a release-1.2.3 blocking requirement.

## 8. Release Exit State

1. Release status: closed.
2. Closure basis: deterministic replay and semantic tests plus real hardware
   evidence for the bounded generic Unit live-ingest path.
3. Follow-up scope moves to the next planned release rather than extending
   release-1.2.3 closure criteria.