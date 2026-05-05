# Release 1.2.2 Real LLM Core Plan

## 1. Overview

Release 1.2.2 starts the first real LLM-driven NeuroLink Core line after the
closed release-1.2.1 Core-Agent baseline. The release goal is to make Core run
through real Microsoft Agent Framework-backed model calls while preserving the
validated 1.2.1 persistence, policy, approval, audit, and Neuro CLI tool
boundaries.

This release does not reopen the release-1.1.10 Unit/demo platform or the
release-1.2.1 hardware stabilization track. The hardware gate is intentionally
bounded to a read-only real Neuro CLI Unit query, and it is required for release
closure. The primary closure proof is that `neurolink_core` can run from user
input through model-backed Affective arbitration, modular Rational planning,
memory lookup/update, policy-gated tool execution, audit sealing, user response,
and a successful read-only real Unit query with recorded evidence.

## 2. Fixed Decisions

1. The Affective Agent uses Microsoft Agent Framework and an OpenAI-compatible
   chat API as the first real model path.
2. Provider configuration is generic and environment-driven. Release 1.2.2 does
   not certify a vendor matrix; it accepts any compatible endpoint that can be
   expressed through `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`.
3. Azure OpenAI variables may remain supported for compatibility, but the 1.2.2
   primary path is the generic OpenAI-compatible interface.
4. The Rational Agent becomes backend-pluggable. GitHub Copilot SDK is the first
   target production backend once its package and API details are available.
5. Rational backends may propose plans only. They must not execute Unit tools,
   bypass leases, bypass approval gates, or call Neuro CLI directly.
6. Mem0 is the intended default long-term memory sidecar. SQLite-backed local
   memory remains the deterministic fallback and test backend.
7. Existing Core policy, lease, approval, tool adapter, payload-status handling,
   and audit layers remain authoritative for all Unit-facing actions.
8. Real model calls are explicit opt-in during development and validation so
   local tests remain deterministic and cost-safe by default.
9. The canonical Neuro CLI release identity is promoted to `RELEASE_TARGET = "1.2.2"`
   after the 1.2.2 closure gates are green.

## 3. Target Architecture Slice

The 1.2.2 Core slice consists of:

1. `neurolink_core.maf`
   - OpenAI-compatible MAF provider configuration, runtime metadata, structured
     Affective model calls, real-provider smoke, and secret-safe diagnostics.
2. `neurolink_core.rational_backends`
   - backend protocol, deterministic fallback backend, Copilot SDK backend, and
     strict RationalPlan validation.
3. `neurolink_core.memory`
   - Mem0 long-term memory sidecar adapter, SQLite fallback, source references,
     memory runtime metadata, and safe unavailable-backend behavior.
4. `neurolink_core.session`
   - prompt-safe session context, compact execution history, pending approval
     context, and bounded context assembly.
5. `neurolink_core.workflow`
   - real-LLM Core workflow path while keeping the 1.2.1 deterministic workflow
     as the offline/test compatibility path.
6. `neurolink_core.cli`
   - runtime selection, provider/backend/memory flags, live-call gating, and
     Agent-readable execution evidence.
7. `neurolink_core.data`
   - additive persistence for memory metadata, model-call evidence, backend
     runtime metadata, and audit traceability if needed.
8. `neurolink_core.tools` and `neuro_cli`
   - unchanged execution boundary unless model-facing manifest fields are
     required. Tool execution stays local and policy-gated.

## 4. Workstreams

### WS-1 Planning And Contract Baseline

1. Add this release plan.
2. Update the HLD to mark release-1.2.2 as the real-LLM Core line.
3. Update AI Core LLD with release-1.2.2 implementation boundaries.
4. Add a Core dependency surface for MAF, Mem0, and the future Copilot SDK
   package entry.
5. Record release kickoff in `PROJECT_PROGRESS.md`.

### WS-2 OpenAI-Compatible MAF Affective Provider

1. Harden provider configuration around `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and
   `OPENAI_MODEL`.
2. Keep diagnostics secret-safe; payloads may report env var names and readiness
   but must not expose credential values.
3. Split provider smoke into availability-only and explicit live-call modes.
4. Add structured-output validation for `AffectiveDecision`.
5. Record model-call evidence without storing prompts or secrets beyond the
   approved audit payload shape.

### WS-3 Modular Rational Backend

1. Introduce a narrow Rational backend protocol.
2. Keep deterministic fake planning as the default test backend.
3. Implement a Copilot SDK backend after SDK package/API details are supplied.
4. Validate every backend result against the live tool manifest.
5. Reject unknown tools, malformed args, unsupported side-effect requests, and
   backend responses that cannot be represented as `RationalPlan`.

### WS-4 Memory Runtime

1. Extend the long-term memory contract with runtime metadata and commit
   semantics.
2. Implement Mem0 sidecar integration for user/session/agent-scoped long-term
   memories.
3. Preserve SQLite local memory as offline fallback.
4. Add source execution span, event, audit, and backend traceability to committed
   memories.
5. Build prompt-safe context that separates interaction, session, long-term, and
   operational memory.

### WS-5 Real LLM Workflow And CLI

1. Generalize the current no-model workflow into a real Core Agent workflow while
   keeping compatibility entrypoints for existing deterministic tests.
2. Add CLI flags for Affective provider, Rational backend, memory backend, and
   explicit live-call approval.
3. Ensure the Affective Agent owns user-visible response policy.
4. Ensure Rational Agent output is treated as internal plan evidence, not direct
   user-facing speech.
5. Preserve approval-gated app lifecycle behavior for all side-effecting tool
   plans.

### WS-6 Validation And Closure

1. Mocked provider/backend tests cover real-runtime wiring without network.
2. OpenAI-compatible smoke proves at least one real Affective model call when
   operator-provided env vars and explicit live-call flags are present.
3. Copilot SDK smoke proves the Rational backend can produce a valid plan under
   strict manifest validation.
4. Memory smoke proves Mem0 participation and SQLite fallback.
5. `agent-run` evidence includes provider/backend/memory runtime metadata,
   database counts, model-call evidence, policy decisions, tool results or
   pending approval, and audit record.
6. Real Neuro CLI hardware smoke is a release gate for read-only Unit query
   execution. The gate must use `--tool-adapter neuro-cli`, require explicit
   real-adapter evidence, and keep side-effecting app control behind approval.

## 5. Validation Gates

1. Documentation gate
   - Release plan, HLD delta, AI Core LLD delta, Core dependency surface, and
     progress entry are present.
2. OpenAI-compatible provider gate
   - Provider readiness is detected from generic OpenAI-compatible env vars.
   - Availability smoke remains non-calling by default.
   - Explicit live-call smoke can execute a real Affective model call and returns
     secret-safe evidence.
3. Rational backend gate
   - Copilot SDK backend is modular and replaceable.
   - Backend output is validated against the manifest before policy evaluation.
4. Memory gate
   - Mem0 backend participates in the real runtime when configured.
   - SQLite fallback remains deterministic and covered by tests.
5. Workflow gate
   - Real runtime runs from user input to final response with persisted events,
     facts, spans, memory records, policy decisions, tool results or approval
     requests, and audit records.
    - Release closure requires a read-only `agent-run` or dry-run through the real
      Neuro CLI tool adapter with adapter runtime evidence and successful tool
      execution recorded in the audit and `agent_run_evidence`.
6. Safety gate
   - No LLM or Copilot backend can bypass policy, lease, approval, payload-status
     failure classification, or audit sealing.
7. Regression gate
   - Existing Core and Neuro CLI tests continue to pass unless intentionally
     updated with compatible contract changes.

## 6. Initial Execution Slices

1. `EXEC-236`: release-1.2.2 kickoff, architecture/LLD baseline, and Core
   dependency surface.
2. `EXEC-237`: OpenAI-compatible provider configuration hardening and real-call
   smoke contract.
3. `EXEC-238`: structured Affective model-call path and validation.
4. `EXEC-239`: Rational backend protocol and deterministic fallback migration.
5. `EXEC-240`: Copilot SDK Rational backend once SDK package/API details are
   provided.
6. `EXEC-241`: Mem0 sidecar backend and SQLite fallback strengthening.
7. `EXEC-242`: prompt-safe session and memory context assembly.
8. `EXEC-243`: real LLM `agent-run` workflow evidence and closure tests.

## 7. Risks And Boundaries

1. GitHub Copilot SDK package/API details are an external dependency. Until they
   are supplied, implementation should land only the backend protocol,
   deterministic fallback, and placeholder-free validation harness.
2. Real model execution can create cost, latency, and credential risk. All live
   calls must stay explicit opt-in and secret-safe.
3. Model output may be malformed or hallucinated. Structured validation and
   manifest allowlisting are release blockers.
4. Mem0 deployment shape may vary. The release should support a configured Mem0
   sidecar and a deterministic SQLite fallback rather than hardcoding one host
   topology.
5. Long-running live event daemons, multi-provider certification, broader
   hardware matrices, and multi-Core federation remain follow-up tracks unless
   explicitly reclassified.

## 8. Definition Of Done

Release 1.2.2 is complete when Core can be demonstrated with real LLM API
participation and recorded evidence:

1. Affective Agent calls a real MAF/OpenAI-compatible provider and returns a
   validated `AffectiveDecision`.
2. Rational Agent is selected through a modular backend interface and the
   Copilot SDK backend can produce a validated `RationalPlan` when configured.
3. Mem0 long-term memory participates in the runtime when configured, with
   SQLite fallback retained for deterministic local use.
4. Policy, approval, lease/resource, tool adapter, payload-status failure, and
   audit boundaries remain intact.
5. `agent-run` emits Agent-readable evidence for provider/backend/memory runtime,
   model-call status, database counts, execution evidence, and final response.
6. A read-only real Neuro CLI hardware gate passes with `--tool-adapter neuro-cli`,
   explicit real-adapter release-gate evidence, and a successful Unit query tool
   result.
7. Core regression tests and affected Neuro CLI tests pass.
8. Remaining daemon, provider-matrix, and federation work is recorded
   as next-release follow-up rather than hidden release debt.

## 9. Closure Plan

Release-1.2.2 is in final closure. The closure rules are:

1. Keep `docs/project/AI_CORE_RUNBOOK.md` and
   `docs/project/AI_CORE_RUNBOOK_ZH.md` as the operator-facing sources for Core
   startup, provider/memory/tool backend selection, and release gate commands.
2. Re-run the final closure validation set immediately before promotion:
   - Affective live model smoke with the validated OpenAI-compatible model.
   - Mem0 sidecar smoke with `fallback_active=false`.
   - Read-only real Neuro CLI adapter gate with successful Unit query evidence.
   - Combined real runtime gate with real Affective, Copilot Rational, Mem0, and
     real Neuro CLI evidence.
   - Core and Neuro CLI regression tests.
3. Promote release identity only after the operator accepts the closure evidence;
   final closure promotes the canonical marker to `RELEASE_TARGET = "1.2.2"`.
4. Record long-running daemon/event-stream validation, provider matrix expansion,
   and broader hardware matrix work as next-release follow-ups unless explicitly
   pulled into the current release.

## 10. Closure Result

Release-1.2.2 is closed against the current Linux operator host and connected
DNESP32S3B evidence set.

Final closure validation passed for:

1. Affective live model smoke with `OPENAI_MODEL=qwen-plus` and
   `call_status=model_call_succeeded`.
2. Mem0 sidecar smoke with `backend_kind=mem0_sidecar`,
   `sidecar_configured=true`, and `fallback_active=false`.
3. Serial-required Linux hardware preflight with `status=ready`, serial device
   `/dev/ttyACM0`, router port `7447`, and read-only Unit query `status=ok`.
4. Read-only real Neuro CLI adapter gate with `real_tool_adapter_present=true`,
   `real_tool_execution_succeeded=true`, and tool result `status=ok`.
5. Combined real runtime gate with `runtime_mode=real_llm`, Affective model call
   evidence, Rational backend `github_copilot_sdk`, Mem0 non-fallback runtime,
   and successful real Neuro CLI tool execution.
6. Core regression suite: `95 passed, 6 subtests passed`.
7. Neuro CLI regression suite: `124 passed`.
8. CRLF-aware `git diff --check` across the NeuroLink repository.

The canonical Neuro CLI release marker is promoted to `RELEASE_TARGET = "1.2.2"`.
Deferred follow-ups remain outside the release gate: long-running daemon/event
stream validation, provider matrix expansion, broader hardware matrix coverage,
and multi-Core federation.