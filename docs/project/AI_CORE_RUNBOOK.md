# NeuroLink AI Core Runbook

This runbook explains how to start and validate `neurolink_core` for the
release-1.2.2 real LLM Core line. It is written for operators and developers who
need to run Core locally, check provider and memory readiness, or execute the
release gates.

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

### 4.2 Provider Readiness Without Model Call

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

### 4.3 Affective Live Model Smoke

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

### 4.4 Mem0 Memory Smoke

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

## 5. Session And Approval Commands

Inspect a Core session:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli session-inspect --session-id <session-id>
```

Inspect a pending approval request:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli approval-inspect --approval-request-id <approval-request-id>
```

Apply an approval decision:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli approval-decision \
  --approval-request-id <approval-request-id> \
  --decision approve \
  --tool-adapter neuro-cli
```

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

`require_real_tool_adapter_requires_neuro_cli_adapter` means a release gate was
requested with the fake adapter. Add `--tool-adapter neuro-cli`.

`serial_device_missing` or `no_reply_board_not_attached` means the board is not
visible in Linux. Run the WSL attach helper and check `/dev/ttyACM*` or
`/dev/ttyUSB*`.

`no_reply_board_unreachable` with `NETWORK_READY` on UART usually means Unit
router endpoint drift. Use `serial zenoh show` and `serial zenoh set` to align
the Unit endpoint with the current host IP.

## 7. Release-1.2.2 Closure Checklist

Before promoting release identity, verify:

1. `maf-provider-smoke --allow-model-call --execute-model-call` succeeds.
2. `no-model-dry-run --memory-backend mem0` succeeds with `fallback_active=false`.
3. hardware preflight returns `status=ready`.
4. real Neuro CLI adapter gate returns `real_tool_execution_succeeded=true`.
5. combined real runtime gate returns `agent_run_evidence.ok=true`.
6. `neurolink_core/tests` pass.
7. `neuro_cli/tests/test_neuro_cli.py` passes.
8. release notes record provider model, Mem0 config shape, hardware endpoint,
   and remaining next-release follow-ups.