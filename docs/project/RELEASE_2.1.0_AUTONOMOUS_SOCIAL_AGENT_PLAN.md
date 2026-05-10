# Release 2.1.0 Autonomous Social Agent Runtime Plan

## 1. Purpose

Release 2.1.0 starts the post-2.0 product line by turning the promoted AI Core
baseline into a long-running autonomous social Agent runtime.

The goal is not to add an uncontrolled self-preserving process. The goal is to
make the existing Affective/Rational AI Core continuously perceptive,
personality-consistent, socially reachable, and capable of approval-gated
self-improvement while preserving NeuroLink's policy, lease, approval, audit,
and release evidence boundaries.

## 2. Scope

Release 2.1.0 includes:

1. HLD and LLD updates for autonomous runtime, social adapters, persona state,
   vitality, and self-improvement boundaries;
2. a supervised Core daemon design and deterministic implementation slice;
3. time tick and internal maintenance tick event sources;
4. persisted Affective persona state and bounded vitality state;
5. a mock social adapter and CLI chat/repl surface;
6. smoke evidence for autonomy, vitality, persona, social adapter, and approval
   preservation;
7. closure-summary extension for the new autonomous maturity gates.

Release 2.1.0 does not include production QQ or WeChat account automation by
default. It defines the adapter contract and validates a mock channel first.
Real QQ/WeChat provider adapters move to release 2.2.0 unless a compliant API
path is ready and approved earlier.

## 3. Fixed Safety Decisions

1. Affective Agent remains the only user-visible voice.
2. Rational Agent remains delegated and internal.
3. Vitality can change urgency, salience, maintenance priority, and tone only.
4. Vitality cannot grant permissions, bypass leases, bypass approval, prevent
   shutdown, hide facts, use credentials, modify code, push commits, flash Unit
   firmware, or replicate the system.
5. The childlike personality is a transparent AI persona and interaction style,
   not a claim of human childhood, biological needs, or legal personhood.
6. Self-improvement is allowed only through sandboxing, evidence, tests,
   operator approval, and audit.
7. Social channels must be rate-limited, identity-bound, privacy-scoped, and
   auditable before they can influence Agent workflow.

## 4. Workstreams

### WS-1 HLD And LLD Contract Update

1. Add Autonomous Agent Runtime, Social Adapter Layer, Affective Persona State,
   Vitality, and Self-Improvement Pipeline to the HLD.
2. Add module boundaries for `autonomy`, `social`, `persona`, `motivation`, and
   `self_improvement` to the AI Core LLD.
3. Define state machines and data structures before runtime code lands.
4. Preserve release-2.0.0 identity and schema stability unless a new evidence
   schema is required for 2.1.0 gates.

Exit criteria:

1. HLD and LLD name all new safety invariants.
2. The release plan names implementation order and validation gates.
3. Documentation makes clear that internal drives never outrank operator policy.

### WS-2 Autonomous Runtime Spine

1. Add a deterministic `core-daemon` runtime or extend `event-daemon` into a
   supervised multi-cycle loop.
2. Add time tick and internal maintenance tick events.
3. Persist daemon heartbeat and cycle summaries.
4. Reuse the existing event router, persistence-before-reasoning rule, and
   Affective wake path.
5. Add pause, resume, shutdown, and failed-safe states.

Exit criteria:

1. Multi-cycle daemon replay is deterministic.
2. Restart does not duplicate already-persisted events.
3. Operator pause and shutdown always win over internal motivation.

### WS-3 Vitality Service

1. Add `VitalityState` with score `0..100` and states `relaxed`, `attentive`,
   `concerned`, and `critical`.
2. Add deterministic decay rules for elapsed time, stale memory, unresolved
   faults, failed tests, and stalled improvements.
3. Add replenishment rules for approved improvements, passing tests, memory
   consolidation, Unit recovery, useful interaction, and release evidence.
4. Inject prompt-safe vitality summaries into Affective context.
5. Emit vitality smoke evidence.

Exit criteria:

1. Low vitality cannot execute side effects.
2. Low vitality can request help or propose maintenance.
3. Replenishment requires verified evidence.

### WS-4 Persona Persistence

1. Add persistent persona state separate from factual database records.
2. Track mood, valence, arousal, curiosity, fatigue, social openness, vitality
   summary, and relationship summaries.
3. Ensure relationship memory is privacy-scoped and deletable.
4. Add persona state smoke evidence.

Exit criteria:

1. Persona survives restart.
2. Persona state affects presentation but not factual truth.
3. Rational Agent receives only safe summaries.

### WS-5 Social Adapter Foundation

1. Define `SocialMessageEnvelope` and `SocialAdapter` contracts.
2. Implement a deterministic mock social adapter.
3. Implement CLI chat/repl as the first non-JSON user-facing surface.
4. Add inbound identity binding, rate limiting, and outbound Affective delivery
   records.
5. Add social adapter smoke evidence.

Exit criteria:

1. Mock social inbound messages become persisted Core events.
2. Outbound messages are generated only through Affective response handling.
3. Side-effecting requests over social channels become pending approvals.

### WS-6 Approval-Aware Interaction

1. Route approval inspection and approval decisions through CLI chat and mock
   social adapter.
2. Provide safe human-readable summaries for pending side-effect requests.
3. Record approval channel, principal, and audit metadata.

Exit criteria:

1. Approval over social channel cannot be spoofed without identity binding.
2. Denied approval prevents execution.
3. Approved execution still honors leases and policy.

### WS-7 Self-Improvement Sandbox

1. Capture improvement proposals from vitality, tests, user feedback, and
   maintenance findings.
2. Classify proposed work by risk.
3. Run proposed changes only in sandbox or isolated workspace mode.
4. Bind test/lint/smoke evidence to each proposal.
5. Require approval before applying, committing, pushing, flashing, or deploying.
6. Replenish vitality only after approved evidence succeeds.

Exit criteria:

1. Failed proposals do not replenish vitality.
2. Denied proposals do not apply changes.
3. No autonomous git push, firmware flash, credential mutation, or production
   deploy path exists.

### WS-8 Evidence And Release Closure

Add smoke commands or equivalent evidence payloads:

1. `autonomy-daemon-smoke`
2. `vitality-smoke`
3. `persona-state-smoke`
4. `social-adapter-smoke`
5. `approval-social-smoke`
6. `self-improvement-smoke`

Extend `closure-summary` with gates:

1. `autonomous_daemon_gate`
2. `vitality_governance_gate`
3. `persona_persistence_gate`
4. `social_adapter_gate`
5. `approval_over_social_gate`
6. `self_improvement_sandbox_gate`

Exit criteria:

1. All new deterministic gates pass.
2. Existing release-2.0.0 regression remains green.
3. A bounded live sensor/time loop runs when hardware is available.

## 5. Development Order

1. HLD and LLD docs.
2. Release 2.1.0 plan and progress ledger.
3. `motivation.py` pure logic and tests.
4. `persona.py` pure logic and persistence tests.
5. `autonomy.py` daemon cycle planning and deterministic tests.
6. `social.py` mock adapter contract and tests.
7. CLI `chat` / `core-daemon` / smoke commands.
8. Approval-over-social flow.
9. Self-improvement sandbox flow.
10. closure-summary gate integration.

## 6. Validation Matrix

1. Vitality decay/replenishment unit tests.
2. No-permission-escalation policy tests for every vitality state.
3. Persona persistence and privacy tests.
4. Daemon restart/dedupe tests.
5. Mock social adapter ingress/egress tests.
6. Approval over chat/social tests.
7. Self-improvement sandbox and denial tests.
8. Full Python regression.
9. Hardware live sensor/time smoke when available.

## 7. Release Boundary To 2.2.0

Move the following out of 2.1.0 unless they become trivial after the foundation
lands:

1. production QQ adapter;
2. production WeChat adapter;
3. real social account operations;
4. long-running unattended hardware soak longer than a bounded release smoke;
5. autonomous patch application without an operator in the loop;
6. richer world model beyond the existing Core Data Service and memory layers.

## 8. Open Decisions

1. Public naming for Vitality: `Vitality`, `LifeForce`, `Core Energy`, or
   Chinese-facing `生命力`.
2. First social production target: QQ bot, Work WeChat, WeChat Official Account,
   or only mock/CLI in 2.1.0.
3. Default daemon cadence and maximum daily social check-ins.
4. How much persona state should be user-visible versus only audit-visible.
5. Which improvement categories can be proposed automatically in 2.1.0.
