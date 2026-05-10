# NeuroLink AI Core User Guide

## 1. What AI Core Does

`neurolink_core` is the Python AI Core for NeuroLink. It turns user input,
Unit events, model decisions, memory recall, and governed tool execution into a
single auditable workflow.

AI Core can run in three useful modes:

1. deterministic local mode for development and release evidence;
2. real-provider mode for Affective model calls through an OpenAI-compatible
   endpoint;
3. bounded real-Unit mode where Core reads events or executes approved Unit
   tools through Neuro CLI adapters.

AI Core does not let models execute Unit tools directly. Models can produce
decisions or plans. Core policy owns tool validation, approvals, leases,
execution, cleanup, and audit evidence.

## 2. Start From A Fresh Shell

Run from the west workspace root:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps
```

Install AI Core dependencies if the environment is new or stale:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m pip install -r applocation/NeuroLink/neurolink_core/requirements.txt
```

Most AI Core commands are run from the NeuroLink project directory:

```bash
cd applocation/NeuroLink
```

Use the module entry point:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli --help
```

## 3. Safety Model

The workflow is intentionally conservative:

1. Affective Agent decides whether a perception frame needs action;
2. Rational Agent may propose a structured plan;
3. Core validates the plan against available tools, Skill rules, MCP mode,
   approval rules, and Unit lease requirements;
4. read-only tools may execute through governed adapters;
5. side-effecting tools create approval requirements and must not run silently;
6. every workflow emits session, audit, policy, memory, and tool evidence.

If a model suggests an unavailable or unsafe tool, the plan is rejected before
adapter execution.

## 4. Quick Health Check

Run a deterministic dry-run first:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli no-model-dry-run --output json
```

Expected high-level result:

1. `status=ok`;
2. `execution_evidence` is present;
3. `closure_gates` are true for audit, memory, plan, and tool evidence;
4. no pending approvals remain for the dry-run.

For a saved database:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli no-model-dry-run --db /tmp/neurolink-core.db --session-id demo-session --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli closure-summary --db /tmp/neurolink-core.db --session-id demo-session --output json
```

## 5. Provider Configuration

Provider calls are always explicit opt-in. Environment variables define the
OpenAI-compatible Affective provider:

```bash
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export OPENAI_MODEL="qwen-plus"
export OPENAI_API_KEY="<secret>"
```

Check provider readiness without executing a model call:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli maf-provider-smoke --output json
```

Execute a live provider smoke only when credentials and cost boundaries are
intentional:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli maf-provider-smoke --execute-model-call --output json
```

If provider requirements are missing, the smoke should fail closed with explicit
missing requirement metadata instead of silently falling back.

## 6. Multimodal And Profile Routing

Use multimodal/profile smoke to confirm input normalization and profile routing:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli multimodal-profile-smoke --text inspect --image-ref frame-001 --output json
```

Important fields:

1. `input_modes` records text/image/audio/video references;
2. `profile_route` records selected profile and readiness;
3. `no_model_call_executed` stays true unless a live call is explicitly
   requested elsewhere.

## 7. Memory Modes

Default local evidence uses deterministic fake memory. Local SQLite memory and
Mem0-backed memory are opt-in paths.

Memory evidence appears in `closure-summary` under:

1. `memory_governance_summary`;
2. `memory_recall_summary`;
3. `aggregate_gates.memory_governance_gate_satisfied`;
4. `aggregate_gates.memory_recall_gate_satisfied`.

Mem0 configuration is environment-driven. Do not commit service credentials or
private memory configuration files.

## 8. Copilot Rational Backend

The Copilot Rational backend is optional and explicit. Configure the Copilot CLI
path when using that backend:

```bash
export GITHUB_COPILOT_CLI_PATH=/home/emb/.local/bin/copilot
```

Live Copilot Rational calls require both backend selection and model-call opt-in:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli agent-run --input-text "inspect current Unit state" --rational-backend copilot --allow-model-call --output json
```

The Rational backend may propose plans only. It cannot run shell commands, call
Neuro CLI directly, execute MCP tools directly, or bypass Core policy.

## 9. Running Agent Workflows

For deterministic local interaction:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli agent-run --input-text "inspect current Unit state" --output json
```

Review these fields:

1. `model_call_evidence`;
2. `rational_plan_evidence`;
3. `tool_results`;
4. `prompt_safe_context`;
5. `approval_requests`.

If a side-effecting operation is requested, Core should record approval context
instead of silently executing the action.

## 10. Real Unit Preflight

Before live Unit rows, return to the west workspace root and confirm the board
is reachable:

```bash
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --attach-only
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --device /dev/ttyACM0 --node unit-01 --capture-duration-sec 30
bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --output json
```

If preflight reports `serial_device_missing`, fix USB/WSL attachment first. If
it reports `no_reply_board_unreachable` while UART shows `NETWORK_READY`, inspect
the Unit Zenoh endpoint:

```bash
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh show --port /dev/ttyACM0
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh set tcp/<host-ip>:7447 --port /dev/ttyACM0
```

## 11. Live Event Smoke

Run a bounded live event probe from the west workspace root when hardware is
ready:

```bash
bash applocation/NeuroLink/scripts/run_unit_live_event_probe.sh --mode update-activate --db /tmp/neurolink-live-event.db --artifact-file build/neurolink_unit_app/neuro_unit_app.llext
```

The listener output should contain a `live-event-smoke` JSON payload with:

1. `status=ok`;
2. `event_source=neuro_cli_events_live`;
3. `live_event_ingest.collected_event_count` greater than zero;
4. `agent_run_evidence.real_tool_adapter_present=true`;
5. `agent_run_evidence.real_tool_execution_succeeded=true`.

Convert that payload into real-scene evidence:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli real-scene-e2e-smoke --live-event-smoke-file <live-event-smoke.json> --output json > <real-scene-e2e-smoke.json>
```

## 12. Release Evidence Commands

Common evidence commands:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli hardware-compatibility-smoke --app-id neuro_unit_app --app-source-dir subprojects/neuro_unit_app --artifact-file /home/emb/project/zephyrproject/build/neurolink_unit_app/neuro_unit_app.llext --required-heap-free-bytes 4096 --required-app-slot-bytes 32768 --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli hardware-acceptance-matrix --app-id neuro_unit_app --app-source-dir subprojects/neuro_unit_app --artifact-file /home/emb/project/zephyrproject/build/neurolink_unit_app/neuro_unit_app.llext --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli resource-budget-governance-smoke --hardware-compatibility-file <hardware-compatibility.json> --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli agent-excellence-smoke --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli signing-provenance-smoke --app-id neuro_unit_app --app-source-dir subprojects/neuro_unit_app --artifact-file /home/emb/project/zephyrproject/build/neurolink_unit_app/neuro_unit_app.llext --output json
```

Diagnosis and rollback evidence:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli observability-diagnosis-smoke --relay-failure-file <relay-failure.json> --activate-failure-file <activate-failure.json> --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli release-rollback-hardening-smoke --activate-failure-file <activate-failure.json> --rollback-file <app-deploy-rollback.json> --output json
```

## 13. Closure Summary

`closure-summary` is the release gatekeeper. It joins session evidence with
saved payload files and reports the validation gate matrix.

For a full release bundle, expected final result is:

1. `validation_gate_summary.ok=true`;
2. `validation_gate_summary.passed_count=20`;
3. `validation_gate_summary.failed_gate_ids=[]`;
4. `validation_gates.closure_summary_gate=true`.

Use the final command shape documented in
`docs/project/RELEASE_2.0.0_FINALIZATION_PLAN.md`.

## 14. Troubleshooting

### `serial_device_missing`

The board is not visible inside the host or WSL environment. From the west
workspace root, reattach USB first:

```bash
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --attach-only
```

### `no_reply_board_unreachable`

The serial device exists but Unit queries do not reply. Check router reachability
and endpoint drift through the serial Zenoh commands in section 10.

### `live_event_ingest_empty`

The live event listener did not collect events. Confirm preflight is ready,
router is running, and the selected probe mode actually triggers Unit events.

### `lease not held` or `lease holder mismatch`

Inspect active leases and release them using the same source agent that acquired
them. Activation and delete resources use different lease resource strings.

### Provider readiness failure

Confirm provider environment variables are present. For smoke tests without a
model call, do not add `--execute-model-call`.

## 15. Where To Go Next

1. Use this guide for startup and common workflows.
2. Use `docs/project/AI_CORE_RUNBOOK.md` for release evidence collection.
3. Use `docs/project/AI_CORE_RUNBOOK_ZH.md` for the Chinese operator runbook.
4. Use `docs/project/RELEASE_2.0.0_FINALIZATION_PLAN.md` for final release work.
5. Use `docs/project/RELEASE_2.0.0_CONTRACT_FREEZE_CHECKLIST.md` for the frozen
   contract boundary.
6. Use `docs/project/RELEASE_2.0.0_REAL_CORE_UNIT_SCENARIO_CHECKLIST.md` for the
   promotion rerun matrix.
