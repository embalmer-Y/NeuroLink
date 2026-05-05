# NeuroLink AI Core 中文运行手册

本文档说明 release-1.2.2 真实 LLM Core 线如何启动、验证和收尾。读者是需要在本机运行 `neurolink_core`、检查模型/记忆配置、执行真实硬件 gate，或接手 release closure 的开发者和操作者。

## 1. Core 运行形态

`neurolink_core` 以 Python CLI 模块运行，工作目录通常是 NeuroLink 项目根目录。Core 的关键原则是：模型只产生情绪决策或内部计划，不能直接执行 Unit 工具。

运行流程如下：

1. 接收用户输入或样例事件。
2. 持久化 perception event 和 fact。
3. 构建 perception frame。
4. 加载 session、历史执行、pending approval 和长期记忆上下文。
5. 执行确定性 Affective arbitration，或执行真实 Affective model call。
6. 让 Rational backend 产生一个内部计划。
7. 使用 tool manifest、policy、approval 和 lease 规则校验计划。
8. 执行允许的只读工具，或为副作用操作生成 approval request。
9. 提交长期记忆候选。
10. 封存 audit 和 Agent-readable evidence。

安全边界必须保持不变：Affective 与 Rational backend 只能返回决策或计划；所有 Unit-facing 动作仍然必须经过 Core policy、approval、lease、tool adapter、payload status 和 audit。

## 2. 基础准备

除非命令显式 `cd` 到其他目录，否则从 west workspace 根目录执行：

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps
```

Core 的模型与记忆依赖独立于 Neuro CLI 依赖：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m pip install -r applocation/NeuroLink/neurolink_core/requirements.txt
```

如果要执行真实硬件 gate，先准备 DNESP32S3B 板卡路径：

```bash
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --attach-only
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --device /dev/ttyACM0 --node unit-01 --capture-duration-sec 30
bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output json
```

如果 preflight 返回 `no_reply_board_unreachable`，但 UART 日志里能看到 `NETWORK_READY`，通常是 Unit 端 Zenoh endpoint 漂移。使用已有 serial Zenoh 命令检查并修正：

```bash
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh show --port /dev/ttyACM0
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh set tcp/<host-ip>:7447 --port /dev/ttyACM0
```

## 3. 环境变量

真实 provider 路径由环境变量驱动。不要把 API key 写入项目文件、文档、提交记录或 `MEM0_CONFIG_JSON`。

OpenAI-compatible Affective provider 需要：

```bash
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export OPENAI_MODEL="qwen-plus"
export OPENAI_API_KEY="<secret>"
```

本机 release-1.2.2 验证中，`qwen-plus` 已通过 OpenAI-compatible live smoke。`qwen3.5-omni-plus` 曾被 provider chat path 拒绝，错误为 `Unsupported model`。

GitHub Copilot Rational backend 需要：

```bash
export GITHUB_COPILOT_CLI_PATH="/home/emb/.local/bin/copilot"
export GITHUB_COPILOT_TIMEOUT="120"
```

GitHub Copilot CLI 必须已经安装并完成 OAuth 授权。

Mem0 sidecar memory backend 需要：

```bash
export MEM0_USER_ID="neurolink-core"
export MEM0_AGENT_ID="neurolink-rational"
export MEM0_CONFIG_JSON='<json without API keys>'
```

当前验证通过的 Mem0 配置形态：

1. LLM provider 为 `openai`，model 为 `qwen-plus`。
2. embedder provider 为 `openai`，model 为 `text-embedding-v4`。
3. embedding dimensions 为 `1536`。
4. vector store 为 `qdrant`。
5. 本地 Qdrant path 为 `/home/emb/.mem0/qdrant`。
6. API key 从 `OPENAI_API_KEY` 继承，不写入 `MEM0_CONFIG_JSON`。

## 4. 常用启动方式

先进入 NeuroLink 项目根目录：

```bash
cd /home/emb/project/zephyrproject/applocation/NeuroLink
```

### 4.1 确定性本地 dry run

用于零网络、零模型调用的基本自检：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli no-model-dry-run
```

预期证据：

1. `runtime_mode=deterministic`。
2. `model_call_evidence.executes_model_call=false`。
3. 默认使用 fake memory 和 fake tool adapter。
4. `agent_run_evidence.ok=true`。

### 4.2 只检查 provider readiness，不调用模型

用于检查依赖、环境变量和 provider readiness，不消耗模型调用：

```bash
source /home/emb/.bashrc
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli maf-provider-smoke
```

预期证据：

1. `status=ready`。
2. `provider_ready_for_model_call=true`。
3. `executes_model_call=false`。
4. 输出中没有 endpoint value 或 API key value。

### 4.3 Affective live model smoke

这会执行真实模型调用，只在需要 live-call validation 时运行：

```bash
source /home/emb/.bashrc
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli maf-provider-smoke --allow-model-call --execute-model-call
```

预期证据：

1. `call_status=model_call_succeeded`。
2. `executes_model_call=true`。
3. `provider_client_kind=agent_framework_openai`。
4. 返回经过校验的 `affective_decision`。

### 4.4 Mem0 memory smoke

这可能通过 Mem0 调用 embedding/model 服务：

```bash
source /home/emb/.bashrc
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli no-model-dry-run --memory-backend mem0 --session-id mem0-real-smoke-001
```

预期证据：

1. `memory_runtime.backend_kind=mem0_sidecar`。
2. `sidecar_configured=true`。
3. `fallback_active=false`。
4. `last_lookup_status=sidecar_and_local_sqlite`。
5. `last_commit_status=sidecar_and_sqlite_mirror`。
6. SQLite mirror evidence 中 `long_term_memories` 非零。

如果 `sidecar_memory_ids` 为空，但 sidecar 已配置、未 fallback、lookup/commit 状态正常，并且 SQLite mirror 有证据，则不一定代表 gate 失败；这可能只是 Mem0 client 返回结构里没有 Core 当前识别的 ID 字段。

### 4.5 只读真实 Neuro CLI tool gate

此命令不调用模型。它证明 Core 可以通过真实 Neuro CLI adapter 执行只读 Unit query：

```bash
source /home/emb/.bashrc
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli agent-run \
  --input-text "Please query current device status for node unit-01." \
  --tool-adapter neuro-cli \
  --require-real-tool-adapter \
  --session-id neuro-cli-gate-readonly
```

预期证据：

1. `agent_run_evidence.ok=true`。
2. `real_tool_adapter_present=true`。
3. `real_tool_execution_succeeded=true`。
4. `tool_adapter_runtime.adapter_kind=neuro-cli`。
5. Unit query payload 包含 `status=ok`、`network_state=NETWORK_READY` 和 `session_ready=true`。

### 4.6 组合真实 runtime gate

这是 release-1.2.2 的完整 Core proof。它会调用 Affective provider、GitHub Copilot、Mem0 和真实 Neuro CLI adapter：

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

预期证据：

1. `agent_run_evidence.ok=true`。
2. `runtime_mode=real_llm`。
3. `model_call_evidence.call_status=model_call_succeeded`。
4. `model_call_evidence.executes_model_call=true`。
5. `rational_backend.backend_kind=github_copilot_sdk`。
6. `memory_runtime.backend_kind=mem0_sidecar`。
7. `memory_runtime.fallback_active=false`。
8. `real_tool_adapter_present=true`。
9. `real_tool_execution_succeeded=true`。

## 5. Session 与 approval 命令

查看 Core session：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli session-inspect --session-id <session-id>
```

查看 pending approval request：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli approval-inspect --approval-request-id <approval-request-id>
```

提交 approval decision：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli approval-decision \
  --approval-request-id <approval-request-id> \
  --decision approve \
  --tool-adapter neuro-cli
```

带副作用的 app control 仍然必须走 approval gate。除非明确要验证这些 gate，否则不要用真实 adapter 执行 app lifecycle 命令。

## 6. 常见故障

`execute_model_call_requires_allow_model_call` 表示命令请求 live model call，但没有带 `--allow-model-call`。

`Unsupported model` 表示 endpoint 和 key 已经连通，但当前 `OPENAI_MODEL` 不被该 provider 的 chat path 支持。使用本文档中已验证的模型，或换成 provider 支持的 chat model。

`copilot_rational_backend_requires_allow_model_call` 表示选择了 `--rational-backend copilot`，但没有带 `--allow-model-call`。

`require_real_tool_adapter_requires_neuro_cli_adapter` 表示请求 release gate 时仍使用 fake adapter。需要加 `--tool-adapter neuro-cli`。

`serial_device_missing` 或 `no_reply_board_not_attached` 表示 Linux 中看不到板卡串口。先运行 WSL attach helper，并检查 `/dev/ttyACM*` 或 `/dev/ttyUSB*`。

`no_reply_board_unreachable` 且 UART 显示 `NETWORK_READY` 时，通常是 Unit router endpoint 漂移。使用 `serial zenoh show` 和 `serial zenoh set` 对齐 Unit endpoint 与当前 host IP。

## 7. Release-1.2.2 收尾 checklist

promote release identity 前，需要确认：

1. `maf-provider-smoke --allow-model-call --execute-model-call` 成功。
2. `no-model-dry-run --memory-backend mem0` 成功，并且 `fallback_active=false`。
3. hardware preflight 返回 `status=ready`。
4. 真实 Neuro CLI adapter gate 返回 `real_tool_execution_succeeded=true`。
5. 组合真实 runtime gate 返回 `agent_run_evidence.ok=true`。
6. `neurolink_core/tests` 通过。
7. `neuro_cli/tests/test_neuro_cli.py` 通过。
8. release notes 记录 provider model、Mem0 config shape、hardware endpoint，以及 deferred next-release follow-up。