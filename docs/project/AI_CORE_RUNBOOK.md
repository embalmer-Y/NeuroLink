# NeuroLink AI Core Runbook

This runbook explains how to start and validate `neurolink_core` on top of the
closed release-1.2.6 federation, relay, and Agent-platform baseline while the
project moves through the active release-1.2.7 productization and
release-2.0.0-readiness line. It still covers the closed release-1.2.5
multimodal governance baseline and the inherited release-1.2.4 Core
orchestrator/live-event-service surfaces that remain part of release evidence.
Release identity is now promoted to `1.2.6`; the next promotion boundary is
release-1.2.7 after its own closure evidence and explicit approval. This
runbook is written for operators and developers who need to run Core locally,
check provider and memory readiness, execute the Core-owned build/deploy gates,
or close bounded live service and AI Core release evidence.

## 1. Runtime Shape

`neurolink_core` runs as a Python CLI module from the NeuroLink project root. It
does not let models execute Unit tools directly. The runtime flow is:

1. ingest a user input or sample event
2. persist perception events and facts
3. build a perception frame
4. load session and memory context
5. run Affective arbitration or a real Affective model call
6. ask the Rational backend for a plan
7. validate the plan against the tool manifest and policy
8. execute allowed read-only tools, or create approval requests for side effects
9. commit memory candidates
10. seal audit and Agent-readable evidence

The important safety boundary is that Affective and Rational backends produce
decisions or plans only. Unit actions still go through Core policy, approval,
lease, tool-adapter, payload-status, and audit checks.

## 2. Prerequisites

Run commands from the west workspace root unless a command explicitly changes
directory.

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps
```

Core model and memory dependencies live separately from Neuro CLI dependencies:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m pip install -r applocation/NeuroLink/neurolink_core/requirements.txt
```

For real hardware gates, prepare the DNESP32S3B board path first:

```bash
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --attach-only
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --device /dev/ttyACM0 --node unit-01 --capture-duration-sec 30
bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output json
```

If preflight reports `no_reply_board_unreachable` while UART shows
`NETWORK_READY`, inspect and correct the Unit router endpoint through the
existing serial Zenoh commands:

```bash
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh show --port /dev/ttyACM0
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh set tcp/<host-ip>:7447 --port /dev/ttyACM0
```

## 3. Environment Variables

The real-provider path is environment-driven. Do not put API keys in project
files.

Required for the OpenAI-compatible Affective provider:

```bash
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export OPENAI_MODEL="qwen-plus"
export OPENAI_API_KEY="<secret>"
```

`qwen-plus` is the model that passed the release-1.2.2 OpenAI-compatible live
smoke on this host. `qwen3.5-omni-plus` was rejected by the provider chat path
as unsupported.

Required for the GitHub Copilot Rational backend:

```bash
export GITHUB_COPILOT_CLI_PATH="/home/emb/.local/bin/copilot"
export GITHUB_COPILOT_TIMEOUT="120"
```

The Copilot CLI must already be installed and authenticated.

Required for the Mem0 sidecar memory backend:

```bash
export MEM0_USER_ID="neurolink-core"
export MEM0_AGENT_ID="neurolink-rational"
export MEM0_CONFIG_JSON='<json without API keys>'
```

The validated release-1.2.2 Mem0 shape uses:

1. LLM provider `openai`, model `qwen-plus`
2. embedder provider `openai`, model `text-embedding-v4`
3. embedding dimensions `1536`
4. vector store `qdrant`
5. local Qdrant path `/home/emb/.mem0/qdrant`
6. API key inherited from `OPENAI_API_KEY`, not embedded in `MEM0_CONFIG_JSON`

## 4. Common Startup Modes

Change into the NeuroLink project root before running Core commands:

```bash
cd /home/emb/project/zephyrproject/applocation/NeuroLink
```

### 4.1 Deterministic Local Dry Run

Use this for a zero-network, zero-model sanity check:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli no-model-dry-run
```

Expected evidence:

1. `runtime_mode=deterministic`
2. `model_call_evidence.executes_model_call=false`
3. fake memory and fake tool adapter unless overridden
4. `agent_run_evidence.ok=true`

### 4.2 Multimodal And Profile Route Smoke

Use this to validate the release-1.2.5 multimodal normalization and inference
profile route contract without executing a model call:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli multimodal-profile-smoke \
  --text inspect \
  --image-ref frame-001
```

Expected evidence:

1. `executes_model_call=false`
2. `closure_gates.multimodal_input_recorded=true`
3. `closure_gates.route_decision_recorded=true`
4. `closure_gates.profile_readiness_recorded=true`
5. `closure_gates.route_ready=true` for a routable request
6. `evidence_summary.selected_profile` records the chosen inference profile

For closure, save the JSON and pass it to `closure-summary` with
`--multimodal-profile-file <multimodal-profile.json>` and
`--require-multimodal-profile`.

### 4.3 Provider Readiness Without Model Call

Use this to check package and provider configuration without spending tokens:

```bash
source /home/emb/.bashrc
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli maf-provider-smoke
```

Expected evidence:

1. `status=ready`
2. `provider_ready_for_model_call=true`
3. `executes_model_call=false`
4. no endpoint values or API key values in output
5. `closure_gates.real_provider_call_opt_in_respected=true`
6. `closure_gates.closure_smoke_outcome_recorded=true`

For real-provider `agent-run` validation, also inspect the session evidence:

1. `model_call_evidence.multimodal_summary` records only prompt-safe counts,
  modes, and short text previews
2. `model_call_evidence.profile_route.selected_profile` records the routed
  provider profile
3. `model_call_evidence.presentation_policy.prompt_safe_multimodal_summary_only=true`
4. `agent_run_evidence.closure_gates.direct_tool_execution_by_model_disabled=true`
5. provider timeout or unavailable profile route failures must fail closed with
  structured error output instead of silent fallback

### 4.4 Affective Live Model Smoke

This executes a real model call. Run only when live-call validation is intended.

```bash
source /home/emb/.bashrc
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli maf-provider-smoke --allow-model-call --execute-model-call
```

Expected evidence:

1. `call_status=model_call_succeeded`
2. `executes_model_call=true`
3. `provider_client_kind=agent_framework_openai`
4. validated `affective_decision`
5. `closure_gates.provider_requirements_ready=true`
6. `closure_gates.model_call_evidence_present=true`
7. `closure_gates.closure_smoke_outcome_recorded=true`

### 4.5 Mem0 Memory Smoke

This may call configured embedding/model services through Mem0.

```bash
source /home/emb/.bashrc
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli no-model-dry-run --memory-backend mem0 --session-id mem0-real-smoke-001
```

Expected evidence:

1. `memory_runtime.backend_kind=mem0_sidecar`
2. `sidecar_configured=true`
3. `fallback_active=false`
4. `last_lookup_status=sidecar_and_local_sqlite`
5. `last_commit_status=sidecar_and_sqlite_mirror`
6. nonzero `long_term_memories` in the SQLite mirror evidence

`sidecar_memory_ids` may be empty if the Mem0 client returns a shape without an
ID field recognized by Core. The release gate relies on active sidecar status,
non-fallback runtime metadata, and SQLite mirror evidence.

### 4.5 Read-Only Real Neuro CLI Tool Gate

This does not call a model. It proves Core can execute a read-only Unit query
through the real Neuro CLI adapter.

```bash
source /home/emb/.bashrc
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli agent-run \
  --input-text "Please query current device status for node unit-01." \
  --tool-adapter neuro-cli \
  --require-real-tool-adapter \
  --session-id neuro-cli-gate-readonly
```

Expected evidence:

1. `agent_run_evidence.ok=true`
2. `real_tool_adapter_present=true`
3. `real_tool_execution_succeeded=true`
4. `tool_adapter_runtime.adapter_kind=neuro-cli`
5. Unit query payload `status=ok`, `network_state=NETWORK_READY`, and
   `session_ready=true`

### 4.6 Combined Real Runtime Gate

This is the full release-1.2.2 Core proof. It calls the Affective provider,
GitHub Copilot, Mem0, and the real Neuro CLI adapter.

```bash
source /home/emb/.bashrc
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli agent-run \
  --input-text "Please query current device status for node unit-01." \
  --maf-provider-mode real_provider \
  --allow-model-call \
  --rational-backend copilot \
  --memory-backend mem0 \
  --tool-adapter neuro-cli \
  --require-real-tool-adapter \
  --session-id release-122-combined
```

Expected evidence:

1. `agent_run_evidence.ok=true`
2. `runtime_mode=real_llm`
3. `model_call_evidence.call_status=model_call_succeeded`
4. `model_call_evidence.executes_model_call=true`
5. `rational_backend.backend_kind=github_copilot_sdk`
6. `memory_runtime.backend_kind=mem0_sidecar`
7. `memory_runtime.fallback_active=false`
8. `real_tool_adapter_present=true`
9. `real_tool_execution_succeeded=true`

## 5. Release-1.2.4 Orchestrator And Live Service Commands

### 5.1 Event Replay And Live-Ingest Baselines

Replay one ordered event fixture through the standard workflow path:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli event-replay \
  --db /tmp/neurolink-core.db \
  --events-file /tmp/activate_failed_events.json
```

Use this to validate `unit.lifecycle.activate_failed` handling, persisted event
facts, and approval-bounded recovery evidence without promoting a live
subscriber yet.

Replay a multi-cycle daemon fixture with shared dedupe and DB-backed restart
continuity:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli event-daemon \
  --db /tmp/neurolink-core.db \
  --events-file /tmp/event_daemon_fixture.json
```

Run the bounded real event-ingest smoke against an app callback subscription:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli live-event-smoke \
  --db /tmp/neurolink-core.db \
  --app-id <app-id> \
  --duration 5 \
  --max-events 1
```

Use this to prove the Core can ingest real Neuro CLI `monitor app-events`
output through the normal workflow path before promoting a long-running live
subscriber.

Run the bounded real event-ingest smoke against the generic Unit event stream:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli live-event-smoke \
  --event-source unit \
  --db /tmp/neurolink-core.db \
  --duration 45 \
  --max-events 4 \
  --ready-file /tmp/neurolink-unit-ready.flag
```

Use this when you need Core to ingest raw `event/**` traffic such as
`lease_event`, `state_event`, or `update_event` rather than only app callback
subscriptions.

For repeatable release-1.2.3 closure probes, use the coordination helper
instead of manually juggling two terminals:

```bash
bash applocation/NeuroLink/scripts/run_unit_live_event_probe.sh \
  --mode state-online
```

Swap `--mode state-online` for `callback` or `update-activate` as needed.

### 5.2 Core App Build And Deploy Orchestrator

Generate the canonical build plan for the default Unit app target:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-build-plan \
  --app-id neuro_unit_app
```

Admit the produced artifact before any deploy action:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-artifact-admission \
  --app-id neuro_unit_app
```

Inspect the protected prepare/verify/activate sequence without executing it:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-deploy-plan \
  --app-id neuro_unit_app \
  --node unit-01
```

Execute the bounded hardware-safe prepare/verify slice through the real Neuro
CLI adapter boundary:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-deploy-prepare-verify \
  --app-id neuro_unit_app \
  --node unit-01 \
  --db /tmp/neurolink-release-124.db
```

Use the activation gate only when the operator explicitly intends to cross the
approval boundary:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-deploy-activate \
  --app-id neuro_unit_app \
  --node unit-01 \
  --approval-decision pending \
  --db /tmp/neurolink-release-124.db
```

Resume with `--approval-decision approve` only after reviewing the pending
approval payload, final artifact path, and release-gate evidence. If activation
health reports `rollback_required`, review the emitted rollback candidate and
use `app-deploy-rollback` with explicit `pending`, `approve`, `deny`, or
`expire` outcomes rather than issuing an ad hoc rollback command.

For the real hardware gate, the minimum successful closure path is one complete
Core-owned `app-build-plan -> app-artifact-admission -> app-deploy-prepare-verify`
sequence with final clean leases.

### 5.3 Event Service Supervision And Restart Continuity

Run the new bounded event service against an app subscription:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli event-service \
  --db /tmp/neurolink-event-service.db \
  --app-id neuro_unit_app \
  --duration 5 \
  --max-events 1 \
  --cycles 2
```

Run the same supervised service against the generic Unit event stream:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli event-service \
  --event-source unit \
  --db /tmp/neurolink-event-service.db \
  --duration 45 \
  --max-events 4 \
  --cycles 2 \
  --ready-file /tmp/neurolink-unit-ready.flag
```

Inspect `event_service.lifecycle`, `event_service.cycle_summaries`,
`event_service.checkpoint`, `event_service.seeded_dedupe_key_count`, and
`event_service.duplicate_event_count` in the JSON output. A healthy bounded
service run now records `start`, `ready`, `events_persisted`, optional
`heartbeat`, optional `restart`, optional `stale_endpoint`, and
`clean_shutdown`.

Use the same `--db` and `--session-id` when validating restart continuity. The
service seeds dedupe state from persisted events, so duplicate callbacks or Unit
events should not retrigger new persisted event rows after restart.

### 5.4 Activation Health Guard

Inspect post-activation health for a target app through the read-only state-sync
surface:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli activation-health-guard \
  --app-id <app-id> \
  --tool-adapter neuro-cli
```

Look for `health_observation.classification` and
`health_observation.ready_for_rollback_consideration`. A
`rollback_required` result is evidence for operator review, not an automatic
rollback.

For `live-event-smoke`, inspect `live_event_ingest.subscription`,
`live_event_ingest.collected_event_count`, `event_source`, and
`agent_run_evidence.real_tool_adapter_present` in the JSON output.

For generic Unit-mode runs, also inspect the persisted topics in the final
response to confirm raw framework payloads were promoted into operational
topics such as `unit.state.online` or `unit.lifecycle.activate_failed`.

### 5.5 Session And Approval Inspection

Inspect a Core session:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli session-inspect --session-id <session-id>
```

Inspect a pending approval request:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli approval-inspect --approval-request-id <approval-request-id>
```

For rollback review, inspect these fields in the JSON output:

1. `approval_context.recovery_candidate_summary`
2. `approval_context.operator_requirements.matching_lease_ids`
3. `approval_context.source_execution_evidence.facts` for `activation_health_observation` and `recovery_candidate`
4. `approval_context.source_execution_evidence.audit_record.payload.activation_health_summary`

For release-1.2.5 provider-backed side-effecting plans, inspect these fields
before approving:

1. `approval_context.operator_requirements.rational_plan_evidence.status`
2. `approval_context.operator_requirements.rational_plan_evidence.selected_tool_name`
3. `approval_context.operator_requirements.rational_plan_evidence.failure_status`
4. `approval_context.source_execution_evidence.audit_record.payload.rational_plan_evidence`

Apply an approval decision:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli approval-decision \
  --approval-request-id <approval-request-id> \
  --decision approve \
  --tool-adapter neuro-cli
```

For a guarded rollback, approve only after the recovery summary, target app,
and rollback lease ownership all line up.

Side-effecting app control remains approval-gated. Do not use the real adapter
for app lifecycle commands unless the operator intends to exercise those gates.

## 6. Troubleshooting

`execute_model_call_requires_allow_model_call` means the command requested a
live model call without `--allow-model-call`.

`Unsupported model` from the provider means the endpoint and key were reached,
but the selected `OPENAI_MODEL` is not valid for that provider path. Use the
validated model in this runbook or select another provider-supported chat model.

`copilot_rational_backend_requires_allow_model_call` means
`--rational-backend copilot` was selected without `--allow-model-call`.

`rational_plan_payload_invalid` or
`rational_plan_tool_not_in_available_tools` means the provider/copilot Rational
response proposed a tool outside the prompt-safe `available_tools` contract or
returned a malformed plan. Treat this as a fail-closed planning outcome: review
`approval_context.operator_requirements.rational_plan_evidence` and the source
audit payload before retrying with a narrower task or corrected provider model.

`require_real_tool_adapter_requires_neuro_cli_adapter` means a release gate was
requested with the fake adapter. Add `--tool-adapter neuro-cli`.

`serial_device_missing` or `no_reply_board_not_attached` means the board is not
visible in Linux. Run the WSL attach helper and check `/dev/ttyACM*` or
`/dev/ttyUSB*`.

`no_reply_board_unreachable` with `NETWORK_READY` on UART usually means Unit
router endpoint drift. Use `serial zenoh show` and `serial zenoh set` to align
the Unit endpoint with the current host IP.

`artifact_header_invalid`, `artifact_identity_missing`, or other
artifact-admission failures usually mean the build output is stale or malformed.
Rebuild through `scripts/build_neurolink.sh --pristine-always` before retrying
the Core admission or deploy path.

`lease_holder_mismatch` on activation or rollback means the lease exists but is
owned by a different `source_agent`. Inspect `query leases` and release the
lease with the matching holder before retrying the Core gate.

For `event-service`, treat these states distinctly:

1. `no_events_collected`: the bounded listener never saw raw events; check your
  trigger path and ready-file coordination.
2. `no_reply`: the monitor path itself is unreachable; run preflight before
  blaming the Core service.
3. `stale_endpoint`: the service observed `unit.network.endpoint_drift`; fix
  the Unit endpoint before expecting stable live service behavior.

## 7. Release-1.2.4 Closure Checklist

Before promoting release identity, verify:

1. `app-build-plan` and `app-artifact-admission` succeed for the target app.
2. one real hardware `app-deploy-prepare-verify` run completes with clean final leases.
3. activation and rollback gates remain approval-bounded and evidence-backed.
4. `event-service` records checkpoint, restart-safe dedupe evidence, and bounded shutdown facts.
5. hardware preflight returns `status=ready`, or a bounded simulated recovery is explicitly documented when unsafe to induce live rollback.
6. `neurolink_core/tests` pass for the touched release slices.
7. `neuro_cli/tests/test_neuro_cli.py` and touched script checks pass.
8. English and Chinese runbooks plus the release plan/README all reflect release-1.2.5 as the closed AI Core release while preserving release-1.2.4 as the inherited orchestrator/live-service baseline.

For release-1.2.5 closure preparation, also verify:

1. provider-backed runs only occur with `--allow-model-call`, and missing provider requirements fail cleanly when the flag or credentials are absent.
2. `execution_evidence.audit_record.payload.rational_plan_evidence` records one of `tool_selected`, `no_tool_selected`, or `invalid_payload` for each provider/copilot Rational outcome.
3. `approval-inspect` exposes `approval_context.operator_requirements.rational_plan_evidence` before any side-effecting provider-proposed tool is approved.
4. `agent_run_evidence.closure_gates.rational_plan_evidence_present=true` and `agent_run_evidence.closure_gates.rational_plan_outcome_recorded=true` whenever provider/copilot Rational planning is exercised.
5. run `closure-summary --session-id <session-id>` against the closure database and verify `aggregate_gates.session_has_execution_evidence=true`, `aggregate_gates.latest_execution_closure_ready=true`, and `aggregate_gates.no_pending_approvals=true` before collecting final evidence.
6. verify `aggregate_gates.memory_governance_gate_satisfied=true`, then inspect `execution_summaries[0].memory_governance_summary` for accepted/rejected candidate counts, committed memory count, rejection reasons, and commit backends.
7. verify `aggregate_gates.memory_recall_gate_satisfied=true`, then inspect `execution_summaries[0].memory_recall_summary` for affective/rational selected counts, filtered categories, backend kind, and fallback continuity.
8. verify `aggregate_gates.tool_skill_mcp_gate_satisfied=true`, then inspect `execution_summaries[0].tool_skill_mcp_summary` for available-tool enforcement, governed side-effect tool counts, workflow-plan requirement, and read-only MCP boundaries.
9. save the documentation closure JSON and pass it through `closure-summary --documentation-file <documentation.json>`; verify `validation_gates.documentation_gate=true`.
10. when provider smoke evidence is required, save the `maf-provider-smoke` JSON and run `closure-summary --provider-smoke-file <provider-smoke.json> --require-provider-smoke`; verify `validation_gates.provider_runtime_gate=true` and `aggregate_gates.provider_smoke_gate_satisfied=true`.
11. when multimodal/profile evidence is required, save the `multimodal-profile-smoke` JSON and run `closure-summary --multimodal-profile-file <multimodal-profile.json> --require-multimodal-profile`; verify `validation_gates.multimodal_normalization_gate=true` and `validation_gates.profile_routing_gate=true`.
12. save regression evidence JSON and pass it through `closure-summary --regression-file <regression.json>`; verify `validation_gates.regression_gate=true`.
13. consume `closure-summary.checklist` as the seven-gate machine-readable release-1.2.5 validation matrix, and use `closure-summary.bundle_checklist` for lower-level bundle items such as `memory_governance_bundle`, `memory_recall_policy_bundle`, and `tool_skill_mcp_bundle`.
14. valid `no_tool_selected` Rational outcomes may have `tool_result_count=0`; closure is still acceptable when `closure_gates.tool_result_outcome_recorded=true` and the Rational evidence records `status=no_tool_selected`.
15. After release-1.2.5 closure evidence passes and promotion is approved, canonical release identity advances from `1.2.4` to `1.2.5`.