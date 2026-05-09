# Release 1.2.5 Multimodal Agent Runtime And Governance Plan

## 1. Overview

Release 1.2.5 advances NeuroLink from the closed release-1.2.4 Core-owned app
build/deploy and live event service baseline into the next HLD-critical slice:
production-shaped AI Core Agent quality.

The release focuses on the HLD requirements that make the Core a strong Agent
runtime rather than only a deterministic operator orchestrator:

1. multimodal Affective Agent input normalization;
2. inference profile routing for local vLLM/OpenAI-compatible backends;
3. memory governance over Mem0 sidecar plus SQLite fallback;
4. safe Agent tool, Skill, and MCP boundaries;
5. policy, approval, and audit evidence around model-proposed actions.

Release 1.2.5 does not promote new Unit update-plane semantics. It builds on
the release-1.2.4 Core-owned app lifecycle evidence and keeps the Unit LLD
control, lease, update, and rollback boundaries authoritative.

## 2. Three-Minor-Release Burn-Down To 2.0.0

The overall HLD completion estimate after release-1.2.4 is about 75%. The goal
is to complete the remaining HLD surface across three development releases and
then enter release-2.0.0 stabilization.

1. `release-1.2.5`: multimodal Agent runtime, inference routing, memory
   governance, and Tool/Skill/MCP safety.
   - Target HLD completion: about 83%.
   - Main outcome: the HLD Affective/Rational Agent and memory/tool governance
     decisions become executable through deterministic tests plus opt-in live
     provider smoke.
2. `release-1.2.6`: Core-to-Core federation and Gateway Unit relay baseline.
   - Target HLD completion: about 91%.
   - Main outcome: topology sync, delegated execution contracts, relay-visible
     Unit attachment, and minimum trust metadata are proven in deterministic
     and bounded live form.
3. `release-1.2.7`: productization hardening and release-2.0.0 readiness.
   - Target HLD completion: about 97%.
   - Main outcome: multi-board build/deploy matrix, resource budget governance,
     release/rollback policy hardening, observability, operator runbooks, and
     full regression/hardware evidence are ready for 2.0.0 promotion.

Release-2.0.0 should be a stabilization, compatibility, and acceptance release:
API/contract freeze, migration notes, final docs, full hardware evidence rerun,
and version promotion.

## 3. HLD And LLD Gap Map

| HLD / LLD surface | Release-1.2.4 status | Release-1.2.5 target |
| --- | --- | --- |
| HLD multimodal Affective Agent | Provider smoke and deterministic Agent seams exist, but multimodal input normalization is not yet a first-class Core contract. | Add normalized multimodal input contract and deterministic normalization for text/image/audio/video references. |
| HLD configurable inference backend | OpenAI-compatible provider detection exists. | Add inference profiles, health probes, route decisions, and fail-closed fallback evidence. |
| HLD Affective/Rational separation | Deterministic Affective/Rational flow exists and provider Rational backend is opt-in. | Preserve separation while making provider-backed decisions schema-validated and tool-manifest bounded. |
| HLD data before reasoning | CoreDataStore persists operational facts and live event evidence. | Ensure Agent context injection uses Core facts first and stores provider/memory decisions as auditable records. |
| HLD long-term memory | Mem0 sidecar plus SQLite fallback exists. | Add candidate screening, accept/reject evidence, retention, dedupe, confidence, source fact references, and fallback continuity. |
| HLD MCP and Skills | Neuro CLI skill is the operator-facing contract; tools are Core contracts. | Promote safe Skill metadata and bounded read-only MCP bridge behavior without bypassing Core policy. |
| AI Core LLD model profile switch lifecycle | Defined in LLD, not fully executable. | Add profile readiness and route decision surfaces with tests for unavailable/unhealthy profiles. |
| AI Core LLD memory candidate lifecycle | Defined in LLD, partially represented by local candidates. | Implement explicit governance states and audit evidence. |
| AI Core LLD audit/policy | Existing approval and release-gate evidence exist. | Extend to provider calls, memory writes, profile routes, and MCP/tool proposals. |

## 4. Fixed Decisions

1. Release identity stays at `1.2.4` during implementation and is promoted to `1.2.5` only after release-1.2.5 closure evidence passes.
2. Deterministic tests remain the default. Real provider and vLLM/OpenAI-compatible
   calls must be opt-in, credential-gated, timeout-bounded, and evidence-backed.
3. Provider-backed Agents may propose actions but must not execute tools directly.
4. The Core policy, approval, lease, and audit layers remain authoritative for
   Tool, Skill, MCP, and Unit operations.
5. Operational facts and Unit telemetry stay in CoreDataStore. Mem0 stores only
   governed long-term memory candidates such as preferences, relationships, and
   distilled operational lessons.
6. Hermes AI Agent and qwenpaw are external reference points only unless their
   source or design documents are added to the workspace. Release-1.2.5 should
   match the quality bar implied by those systems without depending on unavailable
   code.

## 5. Workstreams

### WS-1 Scope Lock And Documentation Baseline

1. Add this release plan.
2. Update README release notes so release-1.2.4 is closed during development,
   then mark release-1.2.5 itself as closed after promotion.
3. Add progress records for release-1.2.5 kickoff and subsequent slices.
4. Keep release identity unpromoted until closure, then promote it to `1.2.5`
   only after explicit approval.

### WS-2 Multimodal Normalization Contract

1. Add a normalized multimodal input schema with text, image, audio, video,
   response modes, profile hint, latency class, and provenance.
2. Implement deterministic normalization first so CI can validate the contract
   without heavyweight local model or media dependencies.
3. Persist or return normalization evidence for Agent workflow debugging.
4. Fail closed for malformed media references or unsupported response modes.

### WS-3 Inference Profile Routing

1. Add profile definitions for `local_16g`, `visual_heavy`, `omni_premium`, and
   remote OpenAI-compatible fallback.
2. Add endpoint readiness and health probe summaries for vLLM/OpenAI-compatible
   providers.
3. Route by input modes, health state, operator override, and resource budget.
4. Persist route decisions and failure reasons.
5. Add tests for healthy default routing, unhealthy local fallback, unsupported
   mode rejection, and operator override bounds.

### WS-4 Affective Agent Provider Runtime

1. Feed normalized multimodal context into the Affective Agent adapter.
2. Require structured Affective decisions and fail closed on invalid provider
   JSON or timeout.
3. Preserve deterministic fake mode for default tests.
4. Record presentation policy evidence so user-visible output cannot pollute
   internal facts.

### WS-5 Rational Planning, Tools, Skills, And MCP

1. Treat `ToolContract` as the authoritative Agent-facing tool manifest.
2. Convert supported Neuro CLI Skill workflow metadata into Core-readable safe
   skill descriptors.
3. Add a bounded read-only MCP bridge only where deterministic policy/audit tests
   can prove it cannot bypass Core gates.
4. Require provider Rational plans to choose at most one available tool or return
   null.
5. Add plan quality checks for available-tool match, required argument coverage,
   side-effect policy, lease/resource fit, retryability, and cleanup awareness.

### WS-6 Memory Governance

1. Extend Mem0 sidecar and local fallback memory with candidate lifecycle states.
2. Add accept/reject reasons, confidence, retention, dedupe keys, and source fact
   references.
3. Keep SQLite mirror evidence for deterministic and fallback operation.
4. Add recall policy separating Affective long-term context from Rational
   operational context.

### WS-7 Approval, Audit, And Closure

1. Extend approval records to Agent-generated side-effecting plans.
2. Seal audit records for provider calls, profile routes, memory writes, and
   Tool/Skill/MCP proposal outcomes.
3. Update English and Chinese AI Core runbooks with 1.2.5 setup, smoke, and
   fallback paths.
4. Run focused regressions and opt-in provider smoke before release identity
   promotion.

## 6. Validation Gates

Release-1.2.5 cannot close until all gates pass:

1. Documentation gate
   - release plan, README, progress records, and English/Chinese runbooks agree
     on release-1.2.5 scope and status.
2. Multimodal normalization gate
   - deterministic tests cover text, image reference, audio reference, video
     placeholder, invalid reference, and unsupported response mode handling.
3. Profile routing gate
   - tests cover default local profile, health-based fallback, operator override,
     and fail-closed unavailable profiles.
4. Provider runtime gate
   - provider-available-no-call smoke reports missing requirements cleanly, and
     real provider calls remain opt-in.
5. Memory governance gate
   - candidate accept/reject, fallback, dedupe, and source fact evidence are
     deterministic and auditable.
6. Tool/Skill/MCP gate
   - provider plans can only select available tools; side-effecting proposals
     require approval; MCP cannot bypass Core policy.
7. Regression gate
   - existing release-1.2.4 app lifecycle and event-service tests remain green.

## 7. Initial Implementation Order

1. Add the release plan and README/progress kickoff alignment.
2. Add deterministic multimodal normalization and profile routing contracts.
3. Add focused tests for normalization and routing.
4. Add memory governance candidate state and tests.
5. Add Tool/Skill/MCP manifest hardening and tests.
6. Add provider-facing Affective/Rational schema hardening and opt-in smoke.
7. Update runbooks and closure evidence.

## 8. Out Of Scope For Release 1.2.5

1. Core-to-Core federation implementation.
2. Gateway Unit relay production path.
3. Multi-board hardware matrix closure.
4. Full cryptographic app signing enforcement.
5. Native omni speech output as a required closure gate.
6. Release-2.0.0 API freeze.

## 9. Initial Progress Estimate

1. Release-1.2.5 implementation progress: about 5% after kickoff documentation.
2. Release-1.2.5 closure progress: 0% until validation gates begin passing.
3. Overall HLD completion at release start: about 75%.
4. Overall HLD completion target at release close: about 83%.