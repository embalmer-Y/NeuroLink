# Release 1.2.1 MAF Core Agent Plan

## 1. Overview

Release 1.2.1 continues the NeuroLink AI Core native Agent track after the
closed release-1.2.0 local baseline. The release goal is to advance the
Python-first AI Core implementation built on Microsoft Agent Framework (MAF),
while preserving the validated Unit control plane, demo app closure, and
Neuro CLI compatibility contracts from earlier releases.

The release does not reopen release-1.1.10 hardware demo scope. Unit firmware,
LLEXT demo apps, and board smoke remain stable unless a later 1.2.1 slice has a
specific Core-Agent integration need and a separate validation gate.

## 2. Fixed Decisions

1. Microsoft Agent Framework is the required Agent framework for AI Core.
2. NeuroLink uses MAF Agents for open-ended Affective/Rational reasoning.
3. NeuroLink uses MAF Workflows for deterministic orchestration, state
   persistence, audit, policy gates, and Unit/tool execution sequencing.
4. Affective Agent owns all user-visible input and output.
5. Rational Agent is invoked only inside a delegated execution window.
6. Unit facts, telemetry, command results, and execution evidence are persisted
   in the Core database before reasoning.
7. MAF native session/history/context facilities provide short-term state.
8. Mem0 remains the long-term semantic memory sidecar.
9. Neuro CLI remains the stable Unit tool surface for release 1.2.1.
10. External CLIs, including Copilot CLI if used, are bounded tools rather than
    the NeuroLink Agent identity.

## 3. Microsoft Agent Framework Usage

The official MAF capability set relevant to NeuroLink includes:

1. `agent-framework` Python package and Python samples.
2. `Agent` objects for model-backed reasoning and tool use.
3. `@tool` function tools with approval-mode support.
4. `AgentSession`, chat history providers, and context providers for short-term
   session state and context injection.
5. Functional workflows for Python-native async orchestration.
6. Graph workflows with executors, edges, type-validated message routing,
   workflow events, checkpointing, and human-in-the-loop patterns.
7. MCP and tool integration surfaces.
8. Hosting options such as local services, OpenAI-compatible endpoints, A2A,
   AG-UI, and durable/serverless hosts.

Release 1.2.1 continues to use Functional Workflow for the current local
vertical slice because the control path remains sequential and easier to test
without depending on real model credentials. The design keeps a clean migration
path to graph workflows when fixed topology, fan-out/fan-in, checkpoint
boundaries, or typed routing become release blockers.

## 4. Target Architecture Slice

The current 1.2.1 Core slice consists of:

1. `neurolink_core.common`
   - IDs, clocks, enums, error envelopes, correlation helpers.
2. `neurolink_core.data`
   - SQLite-backed local Core Data Service MVP.
3. `neurolink_core.workflow`
   - MAF-compatible dry-run workflow skeleton.
4. `neurolink_core.agents`
   - Affective and Rational wrappers with deterministic fake-agent test mode.
5. `neurolink_core.memory`
   - MAF context bridge plus fake Mem0 adapter boundary.
6. `neurolink_core.tools`
   - Neuro CLI adapter and optional external CLI adapter contracts.
7. `neurolink_core.policy`
   - Side-effect classification, approval gates, lease-aware checks.
8. `neurolink_core.audit`
   - Immutable audit record builder and local sink.
9. `neurolink_core.unit`
   - Core-side Unit orchestration DTOs using Neuro CLI and existing protocol
     contracts as the release-1.2.1 execution path.

The first vertical slice ingests a simulated Unit app callback event and a
`time.tick` event, persists both, builds a perception frame, runs Affective
arbitration, optionally calls `system state-sync` through the Neuro CLI adapter,
and seals an audit record. It must run without real model credentials.

## 5. Release Workstreams

### WS-1 Planning And Contract Baseline

1. Create this release plan.
2. Update HLD to clarify MAF Agent vs Workflow responsibilities.
3. Update AI Core LLD with release-1.2.1 implementation boundaries.
4. Record release kickoff in `PROJECT_PROGRESS.md`.

### WS-2 Python Core Skeleton

1. Add the `neurolink_core` package skeleton.
2. Add a local Core CLI entrypoint for version/config/no-model dry-run.
3. Add deterministic fake model, fake memory, and fake tool adapters for tests.
4. Add import and dry-run tests.

### WS-3 Perception And Data MVP

1. Define perception event and time tick envelopes.
2. Add SQLite schema for events, facts, execution spans, policy decisions,
   tool results, memory candidates, and audit records.
3. Add event persistence and in-process notification fan-out.
4. Add tests for event ordering, dedupe tokens, and correlation IDs.

### WS-4 MAF Workflow And Agent Wrappers

1. Add Functional Workflow skeleton for the deterministic Core path.
2. Add Affective Agent wrapper for salience and delegation decisions.
3. Add Rational Agent wrapper for delegated plans and structured results.
4. Add tests for direct answer, no-op perception, delegated read-only tool, and
   blocked side-effect paths.

### WS-5 Neuro CLI Agent-Facing Contracts

1. Add `system tool-manifest --output json`.
2. Add `system state-sync --output json`.
3. Add `monitor agent-events --output jsonl` or a bounded equivalent.
4. Extend `system capabilities --output json` with `agent_runtime`.
5. Preserve existing workflow names, `commands`, `agent_skill`, wrapper path,
   protocol fields, and JSON output behavior.

### WS-6 Policy, Audit, And Tool Execution

1. Define side-effect levels: observe-only, read-only, suggest-only,
   low-risk execute, approval-required, destructive.
2. Gate every tool invocation through policy metadata.
3. Classify Neuro CLI adapter failures using process exit, JSON top-level
   status, nested payload status, parse failure, timeout, and truncation.
4. Seal audit records before terminal success.

### WS-7 Local Vertical Slice Closure

1. Run simulated callback + `time.tick` through the Core workflow.
2. Persist events and audit records locally.
3. Use fake agents by default and skip real provider integration when
   credentials are unavailable.
4. Optionally call Neuro CLI state sync when a local Unit/router is available,
   but do not require hardware for release planning closure.

## 6. Neuro CLI Adjustments

Release 1.2.1 should make Neuro CLI easier for the Core Agent to consume without
breaking existing Agent/skill callers:

1. `system tool-manifest --output json`
   - Emits a neutral NeuroLink tool definition schema.
   - Includes argv templates, required arguments, output contracts, side-effect
     levels, lease/resource requirements, failure statuses, and cleanup hints.
2. `system state-sync --output json`
   - Aggregates device, apps, leases, protocol, serial/router hints, partial
     failures, and recommended next actions.
3. `monitor agent-events --output jsonl`
   - Emits normalized event envelopes one JSON object per line for Core
     ingestion.
   - Preserves decoded CBOR-v2 payloads and payload hex when available.
4. `system capabilities --output json`
   - Adds an `agent_runtime` object for schema versions, tool surfaces, event
     surfaces, side-effect categories, and stable wrapper paths.
5. Agent metadata
   - Standardizes optional `agent_id`, `principal_id`, `execution_span_id`, and
     `correlation_id` where they can be safely echoed without changing Unit wire
     contracts.

## 7. Validation Gates

1. Documentation gate
   - Release plan, HLD delta, AI Core LLD delta, and progress entry are present.
2. Python package gate
   - `neurolink_core` imports and no-model dry-run workflow passes.
3. MAF compatibility gate
   - Deterministic fake client covers workflow behavior; real provider tests are
     skipped unless credentials and packages are present.
4. Data gate
   - SQLite persistence records events, spans, facts, tool results, policy
     decisions, memory candidates, and audit records.
5. CLI compatibility gate
   - Existing Neuro CLI tests still pass after new Agent-facing surfaces land.
6. Tool adapter gate
   - Transport success with payload `status: error` is still failure.
7. Progress gate
   - `PROJECT_PROGRESS.md` records each completed 1.2.1 slice and clearly marks
     local-only, simulated-only, no-model, or hardware-not-run boundaries.

## 7.1 Closure Status

Release 1.2.1 is considered complete for the local AI Core baseline when these
gates are green:

1. `neurolink_core` no-model workflow runs through MAF-shaped Affective and
   Rational Agent adapters.
2. Core persistence includes perception events, execution spans, facts, policy
   decisions, memory candidates, tool results, and audit records.
3. The dry-run output exposes `maf_runtime`, `db_counts`, and
   `execution_evidence` for Agent-readable verification.
4. Neuro CLI exposes `system tool-manifest`, `system state-sync`,
   `monitor agent-events --output jsonl`, and `agent_runtime` capabilities.
5. Bounded agent-events rows include dedupe, causality, raw payload reference,
   payload encoding, and policy tags for Core ingestion.
6. The MAF provider smoke reports `ready` only when the framework package and
   credentials are present; otherwise it reports `skipped` without failing the
   release gate or executing a model call.
7. The canonical Neuro CLI release identity is promoted to
   `RELEASE_TARGET = "1.2.1"`, and the top-level README plus skill references
   describe release-1.2.1 as the active post-baseline Core-Agent development line.

Real model-provider execution, long-running live event daemons, and hardware
smoke are follow-up integration tracks, not blockers for the release-1.2.1 local
baseline closure.

## 7.2 Closure Review (2026-05-05)

Release 1.2.1 is now closed against the repository state and the recorded
execution evidence in `applocation/NeuroLink/PROJECT_PROGRESS.md`.

Acceptance criteria review:

1. MAF-shaped local Core baseline: satisfied.
    - `neurolink_core` runs through deterministic Affective/Rational wrappers,
       persists local execution evidence, and exposes no-model dry-run plus
       provider-smoke entrypoints.
    - the implementation ledger spans the release-1.2.1 Core slices in
       `EXEC-205` through `EXEC-234`.
2. Neuro CLI Agent-facing contract surface: satisfied.
    - `system tool-manifest`, `system state-sync`, `monitor agent-events`, and
       `agent_runtime` capabilities are present on the canonical Neuro CLI path.
    - the Core approval/control path remains grounded in the existing Neuro CLI
       contract instead of introducing a second control plane.
3. Approval-gated resumable Agent behavior: satisfied.
    - pending approvals persist durably, inspection/decision flows are operator
       visible, replay/expiry handling is fail-closed, and approval-time resource
       gates block execution until the required lease is visible.
4. Real command-path and hardware follow-up validation: satisfied for bounded
    release scope.
    - the repository now includes bounded real `start`/`stop`/`restart`/`unload`
       adapter paths plus operator-supervised DNESP32S3B evidence for the real
       approval-decision stop/start flow.
    - default smoke/preflight artifact selection and Linux-side ELF validation
       now reject the stale placeholder-path failure mode discovered during live
       hardware validation.
5. Release identity and top-level documentation: satisfied.
    - the canonical host CLI advertises `RELEASE_TARGET = "1.2.1"`.
    - the top-level README and this plan now describe release-1.2.1 as the
       closed Core-Agent baseline rather than an open-ended in-progress track.

Residual operational notes:

1. Real provider execution with live credentials remains intentionally outside
    the release-1.2.1 closure mark; the current provider smoke stays bounded and
    non-calling when credentials are absent.
2. Long-running live event daemons, broader multi-app hardware coverage, and
    non-Linux operator-path parity remain follow-up tracks for the next release
    line rather than blockers for this closure.
3. Real-board smoke and approval validation still depend on normal operator
    preconditions such as attached serial hardware, a reachable Zenoh router,
    and a valid lease/resource state on the connected board.

## 8. Risks And Boundaries

1. MAF Python APIs are moving quickly; release 1.2.1 must isolate MAF imports
   behind small adapters and keep fake-agent tests independent of real providers.
2. Real model credentials are not required for local gates.
3. Hardware execution is not required for the first Core Agent slice.
4. The Unit CBOR metadata contract still bounds identifiers such as lease IDs;
   Core-generated IDs must stay short where they cross the Unit wire.
5. Core Agent must not bypass Neuro CLI lease, cleanup, and payload-status
   failure rules for existing Unit operations.
6. Continuous event ingestion can create high volume; the first slice uses
   bounded JSONL and SQLite retention policy before any long-running daemon is
   accepted.

## 9. Initial Execution Slices

1. `EXEC-205`: release-1.2.1 MAF Core Agent kickoff and architecture baseline.
2. `EXEC-206`: Python Core package skeleton and no-model dry-run.
3. `EXEC-207`: Core Data Service MVP and perception event persistence.
4. `EXEC-208`: Affective/Rational wrappers and MAF workflow dry-run.
5. `EXEC-209`: Neuro CLI tool manifest and state-sync contract.
6. `EXEC-210`: Agent event JSONL ingestion and local vertical slice closure.

The exact slice numbering can be adjusted if another execution entry lands first,
but release 1.2.1 should keep this separation between architecture, Core runtime,
CLI contracts, and vertical-slice evidence.
