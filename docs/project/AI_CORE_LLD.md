# NeuroLink AI Core LLD

## 1. Overview

This document is the formal low-level design for the NeuroLink AI Core.

It converts the AI Core decisions already fixed by the HLD into executable implementation detail for the Python-first Core runtime built around Microsoft Agent Framework, Mem0, vLLM-compatible inference backends, and the Unit-facing zenoh control fabric.

This document defines:

1. Runtime architecture layers and module boundaries.
2. Internal state machines and execution lifecycles.
3. Core-side durable and non-durable data structures.
4. Contract boundaries to Unit, model serving, memory services, and persistence.
5. Error handling, audit, observability, and recovery semantics.
6. Unit-test requirements and traceability anchors.

This document does not redefine HLD decisions. It operationalizes them.

## 2. Scope and Constraints

### 2.1 Fixed Constraints

1. AI Core primary implementation language is Python.
2. Agent orchestration framework is Microsoft Agent Framework.
3. Short-term state uses MAF native session and context facilities.
4. Long-term semantic memory uses Mem0.
5. Environment facts, Unit telemetry, and execution evidence are stored in the Core database, not in Mem0.
6. User-visible I/O is owned by the Affective Agent.
7. Rational Agent is invoked only by delegation.
8. Unit communication contract must remain compatible with the NeuroLink Unit control plane.

### 2.2 Code Style Constraints

1. This Core document governs Python implementation and does not force Linux Kernel formatting rules onto Python code.
2. Interface names, audit fields, error vocabulary, and traceability IDs must stay aligned with Unit-side design.
3. Every implemented Core subsystem must land with UT in the same execution slice.

## 3. Runtime Architecture

### 3.1 Layered View

The Core runtime is divided into the following layers:

1. `Ingress Layer`
  - Accepts user input, external API requests, operator commands, and Core federation messages.
2. `Workflow Layer`
  - Hosts MAF graph definitions, execution checkpoints, middleware, and orchestration entry points.
3. `Agent Runtime Layer`
  - Hosts Affective Agent and Rational Agent contracts.
4. `Execution Layer`
  - Hosts tool runners, Unit orchestration adapters, code execution sandboxes, and deployment executors.
5. `Data and Memory Layer`
  - Hosts Core Data Service, durable facts database, event bus, Mem0 adapter, and session/history providers.
6. `Policy and Audit Layer`
  - Hosts identity, authorization, lease-awareness, decision records, and immutable audit emission.
7. `Infrastructure Adapter Layer`
  - Hosts zenoh client, vLLM/OpenAI-compatible adapters, storage adapters, and federation transport adapters.

### 3.2 Module Inventory

Recommended top-level Python package layout:

1. `neurolink_core.api`
  - Ingress DTO parsing, API routing, request validation.
2. `neurolink_core.workflow`
  - MAF graphs, workflow node handlers, execution policies.
3. `neurolink_core.agents`
  - Affective Agent adapter, Rational Agent adapter, prompt/input shaping.
4. `neurolink_core.inference`
  - Normalization, profile router, model backend adapter, health probes.
5. `neurolink_core.unit`
  - Unit envelope builder, zenoh requests, deployment execution, response normalization.
6. `neurolink_core.data`
  - Core Data Service, persistence models, repository interfaces.
7. `neurolink_core.memory`
  - Session/history bridge, memory candidate extraction, Mem0 adapter.
8. `neurolink_core.policy`
  - Authorization, capability isolation, lease checks, release policy.
9. `neurolink_core.audit`
  - Audit records, sinks, correlation, redaction rules.
10. `neurolink_core.federation`
  - Core-to-Core topology sync, delegated execution, trust metadata.
11. `neurolink_core.common`
  - Shared envelopes, enums, error model, IDs, clocks, retry policies.

### 3.3 Deployment Units

The Core runtime is expected to run as a single logical application composed of the following deployment units:

1. `core-api`
  - User ingress and operator ingress.
2. `core-workflow`
  - MAF graph host and execution engine.
3. `core-data-service`
  - Database writes, event fan-out, query facade.
4. `core-memory-service`
  - Mem0 extraction and retrieval bridge.
5. `core-unit-orchestrator`
  - Unit command and deployment adapter.

An initial single-process deployment is acceptable. The LLD keeps module boundaries strict so later service splitting remains mechanical.

## 4. Execution Model

### 4.1 Canonical Workflow Nodes

The minimum production workflow graph includes the following nodes:

1. `user_ingress`
2. `multimodal_normalization`
3. `session_context_load`
4. `long_term_memory_lookup`
5. `affective_arbitration`
6. `rational_delegate`
7. `tool_and_unit_execution`
8. `database_persistence`
9. `notification_dispatch`
10. `result_filtering`
11. `user_response`

### 4.2 Execution Span Boundaries

A single workflow invocation creates one `execution span`.

Rules:

1. All child operations inherit the span correlation ID.
2. Unit operations, policy decisions, and memory candidate extraction must record the span ID.
3. A span may contain zero or one Rational Agent delegate windows.
4. A span ends only after persistence and audit emission complete.
5. Failure responses may be released before async notification fan-out finishes, but not before audit emission is queued durably.

## 5. Subsystem Design

### 5.1 Ingress Layer

Responsibilities:

1. Normalize user and operator requests into a common request envelope.
2. Attach `request_id`, `session_id`, `principal_id`, and ingress channel metadata.
3. Reject malformed or unauthorized requests before they enter workflow execution.

### 5.2 Affective Agent Subsystem

Responsibilities:

1. Own all user-visible input interpretation.
2. Read short-term session context and permitted long-term memory context.
3. Decide whether Rational Agent delegation is required.
4. Apply presentation policy to any internal result before user release.

Hard boundary:

1. The Affective Agent may transform presentation.
2. The Affective Agent may not mutate factual database records.
3. The Affective Agent is the default writer of user-facing long-term memory summaries for interactive user sessions.
4. Operator or automation-triggered execution paths may default to Rational-origin metadata when no interactive affective context exists.

### 5.3 Rational Agent Subsystem

Responsibilities:

1. Plan multi-step execution.
2. Invoke tools and Unit actions.
3. Produce structured execution plans and structured results.

Hard boundary:

1. The Rational Agent is not a user-facing endpoint.
2. The Rational Agent may read database facts only within its delegated execution window.
3. The Rational Agent may emit memory candidates but may not directly persist personality memory.

### 5.9 Core CLI Source-Agent Policy (CORE-LLD-AGENT-DEFAULT)

To keep implementation and operations aligned, source-agent defaults are context-dependent:

1. interactive user response path
  - `source_agent=affective` is preferred default.
2. operator CLI or automation path
  - `source_agent=rational` is an allowed default for deterministic execution tooling.
3. explicit command-line or API override
  - caller-provided `source_agent` wins if policy checks pass.

This policy keeps user-facing presentation ownership with Affective Agent while allowing automation and board bring-up flows to use Rational-origin metadata without contract drift.

### 5.4 Inference Subsystem

Responsibilities:

1. Accept normalized multimodal requests.
2. Map profile names to backend model routes.
3. Enforce profile switch safety and fallback behavior.
4. Capture request/response telemetry.

### 5.5 Core Data Service

Responsibilities:

1. Persist Unit events, command results, workflow results, and audit-supporting facts.
2. Publish database update notifications to downstream subscribers.
3. Expose read APIs for workflow execution and investigative queries.
4. Own fact schemas and version sequencing.

### 5.6 Memory Service

Responsibilities:

1. Provide session/history read and write adapters.
2. Extract long-term memory candidates from execution outcomes.
3. Apply dedupe, confidence, and retention policy before Mem0 writes.
4. Keep source fact references for all accepted long-term memories.

### 5.7 Unit Orchestrator

Responsibilities:

1. Translate Core execution plans into Unit control/update/query envelopes.
2. Enforce request metadata contract and correlation IDs.
3. Normalize Unit replies into Core-side result objects.
4. Handle retries, compensation, and deployment sequencing.

### 5.8 Policy and Audit

Responsibilities:

1. Evaluate actor, capability, and lease-aware permissions.
2. Record every allow/deny decision with evidence fields.
3. Emit immutable audit records for critical execution steps.

## 6. State Machines

### 6.1 Session Lifecycle

States:

1. `NEW`
2. `ACTIVE`
3. `IDLE`
4. `RESUMING`
5. `CLOSED`
6. `EXPIRED`

Transitions:

1. `NEW -> ACTIVE`
  - Trigger: first accepted ingress request.
2. `ACTIVE -> IDLE`
  - Trigger: no in-flight execution spans.
3. `IDLE -> RESUMING`
  - Trigger: new request on an existing session.
4. `RESUMING -> ACTIVE`
  - Trigger: session context restored.
5. `IDLE -> EXPIRED`
  - Trigger: retention timeout exceeded.
6. `ACTIVE|IDLE -> CLOSED`
  - Trigger: explicit close or administrative termination.

Persisted fields:

1. `session_id`
2. `principal_id`
3. `last_active_at`
4. `history_pointer`
5. `session_state`

UT anchor: `UT-CORE-SESSION-*`

### 6.2 Delegation Lifecycle

States:

1. `NOT_REQUIRED`
2. `PENDING_DECISION`
3. `DELEGATED`
4. `EXECUTING`
5. `RETURNED`
6. `SUPPRESSED`
7. `FAILED`

Transitions:

1. `PENDING_DECISION -> NOT_REQUIRED`
  - Trigger: Affective Agent answers directly.
2. `PENDING_DECISION -> DELEGATED`
  - Trigger: Affective Agent requests Rational Agent execution.
3. `DELEGATED -> EXECUTING`
  - Trigger: execution window opened.
4. `EXECUTING -> RETURNED`
  - Trigger: structured result accepted.
5. `RETURNED -> SUPPRESSED`
  - Trigger: result filtered from user disclosure.
6. `EXECUTING -> FAILED`
  - Trigger: irrecoverable execution failure.

Persisted fields:

1. `delegation_id`
2. `request_id`
3. `delegate_reason`
4. `execution_span_id`
5. `result_visibility`

UT anchor: `UT-CORE-DELEGATION-*`

### 6.3 Execution Span Lifecycle

States:

1. `CREATED`
2. `READY`
3. `RUNNING`
4. `WAITING_EXTERNAL`
5. `COMPENSATING`
6. `SUCCEEDED`
7. `FAILED`
8. `CANCELLED`

Transitions:

1. `CREATED -> READY`
  - Trigger: context load completes.
2. `READY -> RUNNING`
  - Trigger: node execution begins.
3. `RUNNING -> WAITING_EXTERNAL`
  - Trigger: async tool, Unit, or federation call.
4. `WAITING_EXTERNAL -> RUNNING`
  - Trigger: awaited result received.
5. `RUNNING -> COMPENSATING`
  - Trigger: partial failure after side effects.
6. `RUNNING|COMPENSATING -> SUCCEEDED`
  - Trigger: durable completion path reached.
7. `RUNNING|WAITING_EXTERNAL -> FAILED`
  - Trigger: terminal error.
8. `READY|RUNNING|WAITING_EXTERNAL -> CANCELLED`
  - Trigger: explicit operator or session cancellation.

Persisted fields:

1. `execution_span_id`
2. `workflow_name`
3. `current_node`
4. `started_at`
5. `deadline_at`
6. `terminal_state`

UT anchor: `UT-CORE-SPAN-*`

### 6.4 Unit Command Execution Lifecycle

States:

1. `BUILT`
2. `DISPATCHING`
3. `WAITING_REPLY`
4. `RETRYING`
5. `SUCCEEDED`
6. `FAILED`
7. `COMPENSATED`

Rules:

1. A Core command result is not final until a durable audit record is queued.
2. Retries are allowed only for idempotent or explicitly retryable operations.
3. Lease-sensitive failures must not be retried blindly.

UT anchor: `UT-CORE-UNITEXEC-*`

### 6.5 Deployment Lifecycle

States:

1. `PLANNED`
2. `ARTIFACT_READY`
3. `PREPARING`
4. `VERIFYING`
5. `ACTIVATING`
6. `HEALTH_CHECKING`
7. `COMPLETED`
8. `ROLLING_BACK`
9. `ROLLED_BACK`
10. `FAILED`

Rules:

1. `VERIFYING` cannot start until `PREPARING` is durable and successful.
2. `ACTIVATING` requires a valid lease reference.
3. `ROLLING_BACK` must reference the previous stable artifact.

UT anchor: `UT-CORE-DEPLOY-*`

### 6.6 Model Profile Switch Lifecycle

States:

1. `STABLE`
2. `SWITCH_REQUESTED`
3. `PRELOADING`
4. `HEALTH_CHECKING`
5. `CUTTING_OVER`
6. `DRAINING_OLD`
7. `ROLLED_BACK`
8. `FAILED`

Rules:

1. New requests must not be routed to the target profile until health check succeeds.
2. In-flight requests on the previous profile must be drained unless an emergency cutover policy says otherwise.

UT anchor: `UT-CORE-INFER-*`

### 6.7 Memory Candidate Lifecycle

States:

1. `CREATED`
2. `SCREENING`
3. `ACCEPTED`
4. `REJECTED`
5. `PERSISTED`
6. `RETIRED`

Rules:

1. Candidates always originate from database-backed facts or workflow results.
2. A rejected candidate must retain rejection reason for auditability.

UT anchor: `UT-CORE-MEMORY-*`

### 6.8 Audit Record Lifecycle

States:

1. `OPEN`
2. `APPENDING`
3. `SEALED`
4. `PUBLISHED`
5. `ARCHIVED`

Rules:

1. Critical execution slices must seal an audit record before returning terminal success.
2. Audit records are immutable after sealing.

UT anchor: `UT-CORE-AUDIT-*`

## 7. Data Structures

### 7.1 Request Envelope

```json
{
  "request_id": "req-20260408-0001",
  "session_id": "sess-01",
  "principal_id": "user-01",
  "channel": "chat",
  "input_kind": "user_prompt",
  "payload": {},
  "created_at": "2026-04-08T10:00:00Z"
}
```

### 7.2 Workflow Context

```json
{
  "execution_span_id": "span-01",
  "request_id": "req-20260408-0001",
  "session_id": "sess-01",
  "principal_id": "user-01",
  "affective_context": {},
  "fact_refs": [],
  "memory_refs": [],
  "policy_scope": {},
  "deadline_at": "2026-04-08T10:00:05Z"
}
```

### 7.3 Normalized Multimodal Input

```json
{
  "request_id": "aff-req-001",
  "profile": "local_16g",
  "inputs": {
    "text": ["turn text"],
    "images": ["image-ref-1"],
    "audio": [],
    "video": []
  },
  "response_modes": ["text"],
  "tool_choice": "auto",
  "max_output_tokens": 1024,
  "latency_class": "interactive"
}
```

### 7.4 Delegation Record

```json
{
  "delegation_id": "dlg-01",
  "execution_span_id": "span-01",
  "source_agent": "affective",
  "target_agent": "rational",
  "reason": "requires multi-step deployment",
  "visibility": "internal_only",
  "state": "DELEGATED"
}
```

### 7.5 Core Fact Record

```json
{
  "fact_id": "fact-01",
  "request_id": "req-20260408-0001",
  "node_id": "unit-01",
  "fact_kind": "unit_query_result",
  "version": 43,
  "payload": {},
  "captured_at": "2026-04-08T10:00:02Z"
}
```

### 7.6 Audit Record

```json
{
  "audit_id": "audit-01",
  "execution_span_id": "span-01",
  "request_id": "req-20260408-0001",
  "actor": {
    "principal_id": "user-01",
    "source_agent": "rational"
  },
  "action": "unit_activate",
  "target": "unit-01/app/neuro_demo_app",
  "decision": "allow",
  "evidence": {},
  "state": "SEALED"
}
```

### 7.7 Policy Decision Record

```json
{
  "policy_decision_id": "pd-01",
  "request_id": "req-20260408-0001",
  "subject": "core-a:rational",
  "resource": "update/app/neuro_demo_app/activate",
  "decision": "allow",
  "reason": "valid lease and scope",
  "evaluated_at": "2026-04-08T10:00:03Z"
}
```

### 7.8 Memory Candidate

```json
{
  "memory_candidate_id": "mc-01",
  "memory_scope": "strategy",
  "subject_id": "user-01",
  "source_fact_ids": ["fact-01"],
  "summary": "User prefers confirmation before deployment actions.",
  "confidence": 0.88,
  "state": "CREATED"
}
```

### 7.9 Model Profile Config

```json
{
  "profile": "local_16g",
  "model_id": "gemma-3n-e4b",
  "backend": "vllm",
  "input_modes": ["text", "image", "audio", "video"],
  "output_modes": ["text"],
  "max_context_tokens": 32768,
  "health_state": "STABLE"
}
```

### 7.10 Unit Command Result

```json
{
  "command_execution_id": "uce-01",
  "request_id": "req-20260408-0001",
  "node_id": "unit-01",
  "resource": "update/app/neuro_demo_app/activate",
  "reply_ok": true,
  "reply_code": 0,
  "reply_payload": {},
  "terminal_state": "SUCCEEDED"
}
```

### 7.11 Deployment Plan

```json
{
  "deployment_id": "dep-01",
  "target_node": "unit-01",
  "app_id": "neuro_demo_app",
  "artifact_ref": "artifact://build/neuro_demo_app.llext",
  "required_leases": ["update/app/neuro_demo_app/activate"],
  "steps": ["prepare", "verify", "activate"],
  "rollback_policy": "previous_stable"
}
```

## 8. Error Model

The Core error model is layered:

1. `4000+`
  - request validation
2. `4100+`
  - session and context errors
3. `4200+`
  - policy and authorization errors
4. `4300+`
  - inference and adapter errors
5. `4400+`
  - Unit transport and contract errors
6. `4500+`
  - persistence and audit errors
7. `4600+`
  - memory extraction and retrieval errors
8. `4700+`
  - federation errors

Rules:

1. Unit-native error codes must be preserved inside `details.unit_code`.
2. Core-generated terminal responses must carry both machine-readable and human-debuggable detail.

## 9. Observability

Every execution slice must emit:

1. `request_id`
2. `execution_span_id`
3. `session_id`
4. `delegation_id` if present
5. `target_node` if present
6. `profile` if inference is used
7. `terminal_state`
8. `elapsed_ms`

Critical counters:

1. workflow success rate
2. delegation rate
3. Unit command retry rate
4. deployment rollback rate
5. Mem0 candidate accept rate
6. model switch failure rate

## 10. Unit-Test Design

### 10.1 Test Families

1. `UT-CORE-API-*`
  - envelope validation, malformed input rejection, correlation field injection.
2. `UT-CORE-WORKFLOW-*`
  - node ordering, checkpoint restore, compensation routing.
3. `UT-CORE-DELEGATION-*`
  - affective direct answer, rational delegation, suppressed return path.
4. `UT-CORE-INFER-*`
  - normalization, profile routing, switch rollback, backend timeout.
5. `UT-CORE-DATA-*`
  - DB write-before-notify, version carry-through, query consistency.
6. `UT-CORE-MEMORY-*`
  - candidate extraction, dedupe, rejection, source fact anchoring.
7. `UT-CORE-UNITEXEC-*`
  - envelope build, reply normalization, retry classification, lease-aware failure handling.
8. `UT-CORE-AUDIT-*`
  - seal-before-success, immutability, redaction boundaries.
9. `UT-CORE-FED-*`
  - delegated execution contract, topology merge, trust metadata checks.

### 10.2 Mandatory Traceability Rules

1. Every state machine transition defined in Section 6 must map to at least one UT case.
2. Every external contract object defined in Section 7 must map to one parser/serializer UT case.
3. Every persistence boundary must map to one failure-injection UT case.

## 11. Initial Implementation Order

1. Implement `common` envelopes and IDs.
2. Implement `unit` request/reply adapter with contract UT.
3. Implement `data` persistence models and DB write-before-notify path.
4. Implement `audit` sealing path.
5. Implement minimal MAF workflow skeleton.
6. Implement Affective direct path and Rational delegation path.
7. Implement memory candidate extraction.
8. Implement inference profile routing and health checks.

## 12. Traceability Prefixes

1. `CORE-LLD-ARCH-*`
2. `CORE-LLD-SM-*`
3. `CORE-LLD-DATA-*`
4. `CORE-LLD-UT-*`
