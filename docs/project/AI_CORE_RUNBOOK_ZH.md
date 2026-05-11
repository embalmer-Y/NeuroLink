# NeuroLink AI Core 中文运行手册

本文档说明如何在已完成的 release-2.2.5 persona governance baseline 之上启动、验证和收尾 `neurolink_core`。这个基线是在已提升的 release-2.2.4 Tool/Skill/MCP 与 coding-agent governance baseline 之上继续加入 governed persona seed setup、runtime-evidence-only growth apply、read-only inspect、privacy export/delete，以及 immutability/tamper-report operator path 后形成的。它也继续覆盖已闭环的 release-1.2.6 federation、relay 与 Agent platform 基线、已闭环的 release-1.2.7 HLD completion bundle，以及仍作为 release evidence 继承的 release-1.2.4 到 release-2.2.4 runtime/governance surface。canonical release identity 现已提升到 `2.2.5`，release-2.2.5 bounded completion checklist 已记录，并以 focused persona 与 closure regressions 作为当前完成证据。读者是需要在本机运行 `neurolink_core`、检查模型/记忆配置、执行 Core-owned build/deploy gate，或完成 bounded live service 与 AI Core release evidence 的开发者和操作者。面向日常启动和使用的任务式入口请先阅读 `docs/project/AI_CORE_USER_GUIDE.md`；当前实现路线、promotion 记录与关版日志见 `docs/project/RELEASE_2.2.0_QWENPAW_REFERENCE_FOUNDATION_PLAN.md`、`docs/project/RELEASE_2.2.5_PROMOTION_CHECKLIST.md` 与 `PROJECT_PROGRESS.md`。

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

### 4.2 Multimodal 与 profile route smoke

用于验证 release-1.2.5 的 multimodal normalization 与 inference profile route contract，不执行模型调用：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli multimodal-profile-smoke \
  --text inspect \
  --image-ref frame-001
```

预期证据：

1. `executes_model_call=false`。
2. `closure_gates.multimodal_input_recorded=true`。
3. `closure_gates.route_decision_recorded=true`。
4. `closure_gates.profile_readiness_recorded=true`。
5. 对可路由请求，`closure_gates.route_ready=true`。
6. `evidence_summary.selected_profile` 记录选中的 inference profile。

closure 时，保存该 JSON，并通过 `--multimodal-profile-file <multimodal-profile.json>` 与 `--require-multimodal-profile` 传给 `closure-summary`。

### 4.3 只检查 provider readiness，不调用模型

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
5. `closure_gates.real_provider_call_opt_in_respected=true`。
6. `closure_gates.closure_smoke_outcome_recorded=true`。

对 real-provider `agent-run` 验证，还应检查 session evidence：

1. `model_call_evidence.multimodal_summary` 只记录 prompt-safe 的 modes、count 与短文本预览。
2. `model_call_evidence.profile_route.selected_profile` 记录实际路由到的 provider profile。
3. `model_call_evidence.presentation_policy.prompt_safe_multimodal_summary_only=true`。
4. `agent_run_evidence.closure_gates.direct_tool_execution_by_model_disabled=true`。
5. provider timeout 或 profile route 不可用时，必须以结构化错误 fail-close，不能静默回退。

### 4.4 Affective live model smoke

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
5. `closure_gates.provider_requirements_ready=true`。
6. `closure_gates.model_call_evidence_present=true`。
7. `closure_gates.closure_smoke_outcome_recorded=true`。

### 4.5 Mem0 memory smoke

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

### 4.7 QQ Social Adapter 真实场景预检

对于 release-2.2.2 的真实场景验证，优先先走 `qq_official` 路径。它是当前
更符合官方推荐和生产导向的 QQ 接入方式。`onebot_qq` 保留为兼容桥接路径，
应在官方路径已经跑通并理解其边界后再做补充验证。

release-2.2.2 当前阶段的真实场景目标，不是上线一个长驻 live social daemon，
而是验证官方 adapter profile、三类场景归一化，以及可选的 bounded transport
probe，同时保持 Core policy 与 Affective-only response 的边界不被破坏。

在开始真实场景运行前，操作者需要提供或确认：

1. 官方 QQ endpoint URL；
2. 存放 QQ 凭据的环境变量名；
3. 一个可用于 direct-message 的测试目标；
4. 一个可以安全 @ 机器人的群；
5. 一个可以安全观察“未 @ 机器人消息”的群场景；
6. 是否允许在该 profile 上执行 bounded transport probe。

如果平台能力或当前机器人类型本身不允许官方 QQ 机器人加入目标群，不要把这
件事误判成 Core 实现失败。这种情况下应显式记录平台限制，并先切换到
direct-only 的真实场景 fallback。对于 release-2.2.2，这种 fallback 仍然可以
闭合以下预检内容：

1. 官方 profile readiness；
2. bounded endpoint reachability；
3. direct-message target binding；
4. 群聊与未 @ 场景的确定性 contract evidence。

先显式配置官方 profile：

```bash
cd /home/emb/project/zephyrproject/applocation/NeuroLink
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-config \
  --adapter qq_official \
  --enable \
  --active \
  --endpoint-url <qq-official-endpoint> \
  --credential-env-var <qq-token-env-var> \
  --credential-env-var <qq-secret-env-var> \
  --mention-policy mention_or_direct \
  --transport-kind https \
  --live-network-allowed true
```

然后确认 profile 形态和 readiness 摘要：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-list
```

在任何 transport probe 之前，先跑完全部必测确定性场景：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-test \
  --adapter qq_official \
  --sample-scenario group

/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-test \
  --adapter qq_official \
  --sample-scenario direct

/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-test \
  --adapter qq_official \
  --sample-scenario group_no_mention
```

重点检查这些 JSON 字段：

1. `sample_scenario`
2. `results[0].social_envelope.channel_kind`
3. `results[0].social_envelope.metadata.session_scope`
4. `results[0].social_envelope.metadata.mentioned_user_ids`
5. `evidence_summary.deterministic_normalization.ready_count`

如果群聊接入在平台侧受阻，则把 `group` 与 `group_no_mention` 保留为确定性
contract 检查，并把操作者提供的 direct target 作为这一次真实场景验证中唯一
的 live-scene target。

如果已经明确批准 bounded live-network probe，再对同一个 profile 执行受限
transport reachability probe：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-test \
  --adapter qq_official \
  --sample-scenario group \
  --probe-transport \
  --probe-timeout-seconds 1.5
```

重点检查这些 probe 字段：

1. `probe_requested=true`
2. `results[0].transport_probe.status`
3. `results[0].transport_probe.reason`
4. `results[0].closure_gates.network_execution_policy_respected`
5. `evidence_summary.transport_reachability.status_counts`

这个 transport probe 只证明 endpoint 在受限条件下是否可达，不证明真实回调已
成功送达，也不证明 outbound send 已完成，更不能绕过现有 Core governance。
所有 live social 检查都必须保持显式、受限、且经操作者批准。

如果你已经准备好在本机验证官方 QQ callback ingress，先启动 bounded webhook
server，而不是直接假设已经具备长驻 daemon：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli qq-official-webhook-server \
  --config-file /home/emb/project/zephyrproject/applocation/NeuroLink/config/social_adapter_profiles.json \
  --host 127.0.0.1 \
  --port 8091 \
  --path /qq/callback \
  --duration 30 \
  --max-events 1 \
  --ready-file /tmp/qq-official-webhook-ready.json
```

bounded 运行结束后重点检查：

1. `listen_address.host`、`listen_address.port`、`listen_address.path`
2. `validation_request_count`
3. `dispatch_event_count`
4. `events[0].event_type`
5. `core_results[0].events_persisted`

这个命令的定位只是受限 callback 验证和本地 ingress 验证。它是 release-2.2.2
的第一步 live ingress 能力，不代表最终 production serving topology 已完成。

如果在确认请求路径、`AppID` 和官方请求签名都正确之后，QQ 平台仍持续拒绝
callback 校验，就不要把所有 live ingress 工作都卡死在 callback 页面上，而是
切换到 bounded 官方 gateway 路径：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli qq-official-gateway-client \
  --config-file /home/emb/project/zephyrproject/applocation/NeuroLink/config/social_adapter_profiles.json \
  --duration 30 \
  --max-events 1 \
  --ready-file /tmp/qq-official-gateway-ready.json \
  --session-state-file /tmp/qq-official-gateway-session.json \
  --max-resume-attempts 2
```

bounded 运行结束后重点检查：

1. `gateway.url`
2. `hello_count`
3. `ready_event_count`
4. `dispatch_event_count`
5. `core_results[0].events_persisted`
6. `resume_attempt_count`
7. `resume_success_count`
8. `reconnect_count`

如果当前运行环境允许保存一个本地状态文件，bounded gateway 演练时应优先加上
`--session-state-file`。这样 client 会把 `session_id` 和最新 gateway sequence
落盘，并在断线后执行有限次 `RESUME`，但不会把这条命令提升成一个长驻 daemon。

这条路径的定位是受限官方 websocket/gateway ingress 验证，不代表 Neurolink 已
经具备长驻 QQ resident 服务。

如果要把这次 bounded gateway 运行结果接入 release closure，应先归档 raw run
JSON，再把它转换成稳定的 closure payload，然后再进入最终的
`closure-summary`：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli qq-official-gateway-closure \
  --gateway-run-file /tmp/qq-official-gateway-run.json \
  --require-resume-evidence > /tmp/qq-official-gateway-closure.json
```

随后在最终 `closure-summary` 命令里增加
`--qq-gateway-file /tmp/qq-official-gateway-closure.json`，并确认
`validation_gates.qq_official_gateway_gate=true`。

### 4.7.2 OpenClaw Hosted 兼容 Profile 预检

对于 release-2.2.3 的 additive 验证，`wechat_ilink` 与 `qq_openclaw` 都应被
视为 generic OpenClaw boundary 内的 hosted compatibility profile，而不是已提
升的 direct production route。它们的目标是证明 bounded hosted-profile
normalization、操作者提供的 host/plugin evidence，以及可选的 bounded
gateway ingress，而不是削弱已提升的 `qq_official` 或 direct `wecom` 路径。

在开始 hosted-profile 验证前，操作者需要提供或确认：

1. 一个 OpenClaw gateway host URL；
2. 保存 hosted-profile access token 的环境变量名；
3. plugin identifier 与已验证的 plugin package coordinate；
4. installer/package 元数据，仅作为 evidence，不作为安装动作；
5. 明确的 account/session readiness evidence；
6. 在任何 live-bound 验证前，先显式完成 compliance acknowledgement。

为了在 operator 验证过程中始终保持 release-2.2.3 的边界清晰，建议直接按这张紧凑矩阵判断：

| Adapter | 路径类别 | 在 release-2.2.3 中的角色 | 何时算 ready | 提升姿态 |
| --- | --- | --- | --- | --- |
| `qq_official` | direct official API | 已提升的 QQ 基线 | 官方凭据齐备且确定性检查为绿 | 生产 QQ 主路径 |
| `wecom` | direct gateway/API | 已提升的企业侧路径 | direct endpoint/token 与 bounded gateway evidence 均为绿 | 生产企业路径 |
| `wechat_ilink` | OpenClaw-hosted compatibility | 仅作为 additive hosted validation | host URL、plugin package、session readiness、compliance acknowledgement 齐备 | 若 operator evidence 不完整则 fail closed |
| `qq_openclaw` | OpenClaw-hosted compatibility | 仅作为 additive hosted validation | host URL、plugin package、session readiness、compliance acknowledgement 齐备 | 若 operator evidence 不完整则 fail closed |
| `onebot_qq` | compatibility bridge | 仅用于实验或迁移辅助 | bridge endpoint 与确定性检查为绿 | 不是 promoted QQ replacement |

先显式配置受限的 `qq_openclaw` profile：

```bash
cd /home/emb/project/zephyrproject/applocation/NeuroLink
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-config \
  --adapter qq_openclaw \
  --enable \
  --host-url ws://<openclaw-host> \
  --credential-env-var QQ_OPENCLAW_TOKEN \
  --transport-kind openclaw_gateway \
  --runtime-host openclaw \
  --plugin-id qq_openclaw \
  --plugin-package <operator-supplied-plugin> \
  --installer-package <operator-supplied-installer> \
  --plugin-installed true \
  --account-session-ready true \
  --compliance-acknowledged true
```

在任何 bounded gateway ingress 之前，先完成 hosted-profile 的确定性检查：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-test \
  --adapter qq_openclaw \
  --sample-scenario group

/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-test \
  --adapter qq_openclaw \
  --sample-scenario direct

/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli social-adapter-smoke
```

重点检查这些 JSON 字段：

1. `results[0].profile.runtime_host`
2. `results[0].profile.transport_kind`
3. `results[0].profile.missing_requirements`
4. `results[0].social_envelope.metadata.plugin_id`
5. `results[0].social_envelope.metadata.plugin_package`
6. `social-adapter-smoke` 输出中的 `closure_gates.qq_openclaw_social_gate`

如果已经批准 bounded OpenClaw ingress，应先归档 raw gateway run，再在 release
closure 前把它转换成稳定的 closure evidence：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli openclaw-gateway-client \
  --config-file /home/emb/project/zephyrproject/applocation/NeuroLink/config/social_adapter_profiles.json \
  --adapter qq_openclaw \
  --gateway-url ws://<openclaw-host> \
  --plugin-package <operator-supplied-plugin> \
  --duration 15 \
  --max-events 1 > /tmp/openclaw-gateway-run.json

/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli openclaw-gateway-closure \
  --gateway-run-file /tmp/openclaw-gateway-run.json > /tmp/openclaw-gateway-closure.json
```

随后在最终 `closure-summary` 命令里增加
`--openclaw-gateway-file /tmp/openclaw-gateway-closure.json`，并确认
`validation_gates.openclaw_gateway_gate=true`。

对于默认的 release-2.2.3 预提测回归，优先直接执行这条已经打包好的固定验证命令，
不要再手工重拼 focused pytest 过滤条件：

```bash
cd /home/emb/project/zephyrproject
bash applocation/NeuroLink/scripts/run_release_2_2_3_pre_promotion_validation.sh
```

### 4.7.1 QQ 官方 Webhook Callback 联调清单

当你准备把 QQ 官方开发者平台真正接到这条 bounded 本地 ingress 路径上时，按
这份清单执行。目标不是直接上线常驻服务，而是先证明真实 callback 能到达
Core。

在打开 QQ 开发者平台之前，先确认本地前置条件：

1. 当前 shell 中已经有 `QQ_BOT_APP_ID` 和 `QQ_BOT_APP_SECRET`；
2. `social-adapter-list` 显示 `qq_official` 已 active 且 ready；
3. 确定性 `group`、`direct`、`group_no_mention` 检查已经通过；
4. 操作者已经准备好一个可转发到 `127.0.0.1:<local-port>` 的临时公网 HTTPS 入口。

先启动 bounded listener，并在配置官方 callback 时保持这个终端不退出：

```bash
cd /home/emb/project/zephyrproject/applocation/NeuroLink
source /home/emb/project/zephyrproject/.venv/bin/activate
python -m neurolink_core.cli qq-official-webhook-server \
  --config-file /home/emb/project/zephyrproject/applocation/NeuroLink/config/social_adapter_profiles.json \
  --host 127.0.0.1 \
  --port 8091 \
  --path /qq/callback \
  --duration 120 \
  --max-events 1 \
  --ready-file /tmp/qq-official-webhook-ready.json
```

在第二个终端读取 ready-file，确认本地实际监听地址后再做公网暴露：

```bash
cat /tmp/qq-official-webhook-ready.json
```

预期 ready-file 结构：

```json
{
  "host": "127.0.0.1",
  "path": "/qq/callback",
  "port": 8091
}
```

然后在 QQ 官方平台侧配置 callback，并通过操作者自管的公网 HTTPS 转发接入：

1. 创建或复用一个临时公网 HTTPS URL，并把它转发到 `http://127.0.0.1:8091/qq/callback`；
2. 在 QQ 开发者平台的 callback URL 中填写 `<public-https-base>/qq/callback`；
3. 平台使用的 `AppID`、`AppSecret` 必须与当前 active 的 `qq_official` profile 一致；
4. 保存平台 callback 配置时，确保本地 bounded listener 仍然在运行。

bounded 运行结果分两步解读：

1. `validation_request_count=1` 说明 QQ 官方已经打到 callback，且本地签名逻辑完成了验证响应；
2. `dispatch_event_count=1` 且 `core_results[0].events_persisted=1` 说明至少有一个受支持的 live event 已经跨过 webhook 边界并进入 Core。

如果 callback 验证成功，但在超时前没有 dispatch 事件到达，应把这次运行视为
transport-only proof。它可以证明 ingress 可达，但还不能证明真实消息事件链路。
这时应在同一个 bounded 窗口内，主动给 bot 发一条 direct message，或者触发
一次受支持的 mention 事件，然后重试。

如果 QQ 平台在保存 callback 时立刻报错，先检查这几项：

1. 公网 URL 是否为 HTTPS，且转发到了 ready-file 中同一个 `path`；
2. 当前运行 shell 中的 `AppSecret` 是否与 active profile 绑定一致；
3. bounded listener 是否已经因为 `duration` 或 `max-events` 提前退出；
4. 转发层是否完整保留了 POST body 和 content type。

## 5. Release-1.2.4 编排与实时服务命令

### 5.1 事件回放与 live-ingest 基线

通过标准 workflow 路径回放一组有序事件 fixture：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli event-replay \
  --db /tmp/neurolink-core.db \
  --events-file /tmp/activate_failed_events.json
```

这个命令用于验证 `unit.lifecycle.activate_failed` 的处理、事件持久化事实，以及
approval-bounded recovery evidence，而不需要先把 live subscriber 提升为 release gate。

回放多轮 daemon fixture，用于验证跨轮 dedupe 和 DB-backed restart continuity：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli event-daemon \
  --db /tmp/neurolink-core.db \
  --events-file /tmp/event_daemon_fixture.json
```

执行 bounded real event-ingest smoke，直接对 app callback 订阅做 Core 侧摄取验证：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli live-event-smoke \
  --db /tmp/neurolink-core.db \
  --app-id <app-id> \
  --duration 5 \
  --max-events 1
```

这个命令用于证明 Core 可以把真实 Neuro CLI `monitor app-events` 输出接入标准
workflow，而无需先把长驻 live subscriber 提升为 release gate。

执行 bounded real event-ingest smoke，直接对通用 Unit `event/**` 订阅做 Core 侧摄取验证：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli live-event-smoke \
  --event-source unit \
  --db /tmp/neurolink-core.db \
  --duration 45 \
  --max-events 4 \
  --ready-file /tmp/neurolink-unit-ready.flag
```

当你需要让 Core 摄取原始 `lease_event`、`state_event`、`update_event` 等
通用 Unit framework 事件，而不是只看 app callback 时，使用这个模式。

如果要重复做 release-1.2.3 closure probe，优先使用协同脚本，而不是手工开两个终端：

```bash
bash applocation/NeuroLink/scripts/run_unit_live_event_probe.sh \
  --mode state-online
```

`--mode` 可切换为 `callback` 或 `update-activate`。

### 5.2 Core App Build 与 Deploy 编排

先生成默认 Unit app 目标的 canonical build plan：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-build-plan \
  --app-id neuro_unit_app
```

在任何 deploy 动作之前，先执行 artifact admission：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-artifact-admission \
  --app-id neuro_unit_app
```

只查看受保护的 `prepare -> verify -> approval -> activate -> cleanup` 序列，而不实际执行：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-deploy-plan \
  --app-id neuro_unit_app \
  --node unit-01
```

通过真实 Neuro CLI adapter 执行 bounded、硬件相对安全的 prepare/verify slice：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-deploy-prepare-verify \
  --app-id neuro_unit_app \
  --node unit-01 \
  --db /tmp/neurolink-release-124.db
```

只有在操作者明确要跨越 approval boundary 时，才使用 activation gate：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli app-deploy-activate \
  --app-id neuro_unit_app \
  --node unit-01 \
  --approval-decision pending \
  --db /tmp/neurolink-release-124.db
```

只有在审查完 pending approval payload、artifact path 和 release-gate evidence 之后，才用 `--approval-decision approve` 继续。如果 activation health 返回 `rollback_required`，应审查 emitted rollback candidate，并通过 `app-deploy-rollback` 的 `pending`、`approve`、`deny` 或 `expire` 结果推进，而不是临时执行脱离 Core 的 rollback。

对真实硬件 gate，最小成功 closure 路径是一条完整的 Core-owned `app-build-plan -> app-artifact-admission -> app-deploy-prepare-verify` 流程，并保证最终 leases 已清理干净。

### 5.3 Event Service 监督与重启连续性

针对 app 级订阅运行新的 bounded event service：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli event-service \
  --db /tmp/neurolink-event-service.db \
  --app-id neuro_unit_app \
  --duration 5 \
  --max-events 1 \
  --cycles 2
```

针对通用 Unit `event/**` 流运行同一监督式服务：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli event-service \
  --event-source unit \
  --db /tmp/neurolink-event-service.db \
  --duration 45 \
  --max-events 4 \
  --cycles 2 \
  --ready-file /tmp/neurolink-unit-ready.flag
```

重点检查 JSON 输出中的 `event_service.lifecycle`、`event_service.cycle_summaries`、`event_service.checkpoint`、`event_service.seeded_dedupe_key_count` 和 `event_service.duplicate_event_count`。健康的 bounded service 现在会记录 `start`、`ready`、`events_persisted`、可选的 `heartbeat`、可选的 `restart`、可选的 `stale_endpoint`，以及 `clean_shutdown`。

如果要验证 restart continuity，请复用相同的 `--db` 和 `--session-id`。服务会从已持久化事件中 seed dedupe state，因此重启后的重复 callback 或 Unit event 不应再次写入新的 perception event 行。

### 5.4 Activation Health Guard

通过只读 state-sync 面观察指定 app 的激活后健康状态：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli activation-health-guard \
  --app-id <app-id> \
  --tool-adapter neuro-cli
```

重点查看 `health_observation.classification` 和
`health_observation.ready_for_rollback_consideration`。如果结果是
`rollback_required`，表示进入 operator review，而不是自动回滚。

对 `live-event-smoke`，重点查看输出中的 `live_event_ingest.subscription`、
`live_event_ingest.collected_event_count`、`event_source`，以及
`agent_run_evidence.real_tool_adapter_present`。

对于 generic Unit 模式，还要检查最终 response 中的 topics，确认原始 framework
事件已经被提升为 `unit.state.online`、`unit.lifecycle.activate_failed` 等
operational topic，而不是停留在低层事件名。

### 5.5 Session 与 approval 检查

查看 Core session：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli session-inspect --session-id <session-id>
```

查看 pending approval request：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli approval-inspect --approval-request-id <approval-request-id>
```

针对 guarded rollback，重点检查以下 JSON 字段：

1. `approval_context.recovery_candidate_summary`
2. `approval_context.operator_requirements.matching_lease_ids`
3. `approval_context.source_execution_evidence.facts` 中的 `activation_health_observation` 与 `recovery_candidate`
4. `approval_context.source_execution_evidence.audit_record.payload.activation_health_summary`

针对 release-1.2.5 中 provider 驱动的带副作用计划，在批准前还要检查：

1. `approval_context.operator_requirements.rational_plan_evidence.status`
2. `approval_context.operator_requirements.rational_plan_evidence.selected_tool_name`
3. `approval_context.operator_requirements.rational_plan_evidence.failure_status`
4. `approval_context.source_execution_evidence.audit_record.payload.rational_plan_evidence`

提交 approval decision：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli approval-decision \
  --approval-request-id <approval-request-id> \
  --decision approve \
  --tool-adapter neuro-cli
```

只有当 recovery summary、target app、rollback lease ownership 三者一致时，才批准 guarded rollback。

带副作用的 app control 仍然必须走 approval gate。除非明确要验证这些 gate，否则不要用真实 adapter 执行 app lifecycle 命令。

## 6. 常见故障

`execute_model_call_requires_allow_model_call` 表示命令请求 live model call，但没有带 `--allow-model-call`。

`Unsupported model` 表示 endpoint 和 key 已经连通，但当前 `OPENAI_MODEL` 不被该 provider 的 chat path 支持。使用本文档中已验证的模型，或换成 provider 支持的 chat model。

`copilot_rational_backend_requires_allow_model_call` 表示选择了 `--rational-backend copilot`，但没有带 `--allow-model-call`。

`rational_plan_payload_invalid` 或 `rational_plan_tool_not_in_available_tools` 表示 provider/copilot 的 Rational 响应提出了不在 prompt-safe `available_tools` 合约中的工具，或者返回了格式错误的 plan。这类情况必须按 fail-closed 处理：先检查 `approval_context.operator_requirements.rational_plan_evidence` 和源 audit payload，再决定是否缩小任务范围或调整 provider model 后重试。

`require_real_tool_adapter_requires_neuro_cli_adapter` 表示请求 release gate 时仍使用 fake adapter。需要加 `--tool-adapter neuro-cli`。

`serial_device_missing` 或 `no_reply_board_not_attached` 表示 Linux 中看不到板卡串口。先运行 WSL attach helper，并检查 `/dev/ttyACM*` 或 `/dev/ttyUSB*`。

`no_reply_board_unreachable` 且 UART 显示 `NETWORK_READY` 时，通常是 Unit router endpoint 漂移。使用 `serial zenoh show` 和 `serial zenoh set` 对齐 Unit endpoint 与当前 host IP。

`artifact_header_invalid`、`artifact_identity_missing` 或其他 artifact-admission 失败，通常表示 build output 已陈旧或格式异常。应先通过 `scripts/build_neurolink.sh --pristine-always` 重建，再重试 Core admission 或 deploy 路径。

activation 或 rollback 中出现 `lease_holder_mismatch`，表示 lease 确实存在，但当前持有者不是你请求的 `source_agent`。先检查 `query leases`，按正确 holder 释放 lease，再重试 Core gate。

对 `event-service`，需要明确区分以下状态：

1. `no_events_collected`：bounded listener 没看到任何原始事件，需要检查 ready-file 协调和触发路径。
2. `no_reply`：monitor 路径本身不可达，应先运行 preflight，而不是直接怀疑 Core service。
3. `stale_endpoint`：服务观察到了 `unit.network.endpoint_drift`，应先修复 Unit endpoint，再期待稳定 live service。

## 7. Release-1.2.4 收尾 checklist

promote release identity 前，需要确认：

1. `app-build-plan` 与 `app-artifact-admission` 对目标 app 成功。
2. 至少一条真实硬件 `app-deploy-prepare-verify` 流成功完成，并保证最终 leases 干净。
3. activation 与 rollback gate 保持 approval-bounded，并且 evidence 完整。
4. `event-service` 已记录 checkpoint、restart-safe dedupe evidence 和 bounded shutdown facts。
5. hardware preflight 返回 `status=ready`；如果 live rollback 不安全，需明确记录 bounded simulated recovery 的理由。
6. `neurolink_core/tests` 中本 release 触达的 slice 全部通过。
7. `neuro_cli/tests/test_neuro_cli.py` 和触达的 script checks 通过。
8. 英文/中文 runbook、release plan 和 README 都已把 release-1.2.5 标记为已闭环的 AI Core release，并保留 release-1.2.4 作为继承的 orchestrator/live-service baseline。

针对 release-1.2.5 的 closure 准备，还需要确认：

1. provider 路径只在显式带上 `--allow-model-call` 时运行；缺少 flag 或 credentials 时，系统能给出干净的缺失前提错误。
2. 每次 provider/copilot Rational 结果都会在 `execution_evidence.audit_record.payload.rational_plan_evidence` 中记录 `tool_selected`、`no_tool_selected` 或 `invalid_payload` 三类之一。
3. 对任何 provider 提议的带副作用工具，`approval-inspect` 都会先暴露 `approval_context.operator_requirements.rational_plan_evidence`，供 operator 审查。
4. 一旦实际走过 provider/copilot Rational 规划，`agent_run_evidence.closure_gates.rational_plan_evidence_present=true` 且 `agent_run_evidence.closure_gates.rational_plan_outcome_recorded=true`。
5. 针对 closure 使用的数据库运行 `closure-summary --session-id <session-id>`，确认 `aggregate_gates.session_has_execution_evidence=true`、`aggregate_gates.latest_execution_closure_ready=true` 与 `aggregate_gates.no_pending_approvals=true` 后，再收集最终 evidence。
6. 确认 `aggregate_gates.memory_governance_gate_satisfied=true`，并检查 `execution_summaries[0].memory_governance_summary` 中的 accepted/rejected candidate 数量、committed memory 数量、rejection reasons 与 commit backends。
7. 确认 `aggregate_gates.memory_recall_gate_satisfied=true`，并检查 `execution_summaries[0].memory_recall_summary` 中的 affective/rational selected counts、filtered categories、backend kind 与 fallback continuity。
8. 确认 `aggregate_gates.tool_skill_mcp_gate_satisfied=true`，并检查 `execution_summaries[0].tool_skill_mcp_summary` 中的 available-tool enforcement、governed side-effect tool counts、workflow-plan requirement 与只读 MCP boundary。
9. 保存 documentation closure JSON，并通过 `closure-summary --documentation-file <documentation.json>` 传入；确认 `validation_gates.documentation_gate=true`。
10. 当 closure 要求 provider smoke evidence 时，先保存 `maf-provider-smoke` JSON，再运行 `closure-summary --provider-smoke-file <provider-smoke.json> --require-provider-smoke`；确认 `validation_gates.provider_runtime_gate=true` 且 `aggregate_gates.provider_smoke_gate_satisfied=true`。
11. 当 closure 要求 multimodal/profile evidence 时，先保存 `multimodal-profile-smoke` JSON，再运行 `closure-summary --multimodal-profile-file <multimodal-profile.json> --require-multimodal-profile`；确认 `validation_gates.multimodal_normalization_gate=true` 与 `validation_gates.profile_routing_gate=true`。
12. 保存 regression evidence JSON，并通过 `closure-summary --regression-file <regression.json>` 传入；确认 `validation_gates.regression_gate=true`。
13. 优先消费 `closure-summary.checklist` 作为七个 release gate 的机器可读矩阵，并使用 `closure-summary.bundle_checklist` 查看 `memory_governance_bundle`、`memory_recall_policy_bundle` 与 `tool_skill_mcp_bundle` 等底层 bundle 项。
14. 合法的 `no_tool_selected` Rational 结果可以有 `tool_result_count=0`；只要 `closure_gates.tool_result_outcome_recorded=true` 且 Rational evidence 记录 `status=no_tool_selected`，closure summary 仍可接受。
15. 在 release-1.2.5 closure evidence 全部通过且批准 promotion 后，canonical release identity 从 `1.2.4` 提升到 `1.2.5`。

针对 release-1.2.7 的最终 closure bundle，继续沿用同一套 file-driven
evidence 流程，并把新增的两个独立 gate 接入最后一次 `closure-summary`：

16. 先保存 relay failure closure JSON，以及 `app-deploy-activate` 返回
  `rollback_required` 的 payload，再生成结构化 diagnosis payload：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli observability-diagnosis-smoke --relay-failure-file <relay-failure.json> --activate-failure-file <activate-failure.json> --output json > <observability-diagnosis-smoke.json>
```

17. 再保存同一份 `app-deploy-activate` failure payload 与对应的
  `app-deploy-rollback` payload，生成 guarded rollback closure payload：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli release-rollback-hardening-smoke --activate-failure-file <activate-failure.json> --rollback-file <app-deploy-rollback.json> --output json > <release-rollback-hardening-smoke.json>
```

18. 保存 `hardware-compatibility-smoke` payload 后，再生成独立的
  resource-budget governance closure payload：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli resource-budget-governance-smoke --hardware-compatibility-file <hardware-compatibility.json> --output json > <resource-budget-governance-smoke.json>
```

19. 为 release-2.0.0 rerun 准备可归档 checklist 时，可直接生成新的
  skeleton：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli real-scene-checklist-template --release-target 2.0.0 --implementation-release 1.2.7 --output json > <real-scene-checklist.json>
```

  也可以直接从
  `docs/project/RELEASE_2.0.0_REAL_CORE_UNIT_SCENARIO_CHECKLIST.template.json`
  或已填充示例
  `docs/project/RELEASE_2.0.0_REAL_CORE_UNIT_SCENARIO_CHECKLIST.example.json`
  起步，再把其中 archive path 替换成当前 rerun bundle 的路径。

20. 最终运行 release-1.2.7 的 `closure-summary` 时，把这些新 payload
  一起带进去，确保 `validation_gates.resource_budget_governance_gate=true`、
  `validation_gates.release_rollback_hardening_gate=true` 与
  `validation_gates.observability_diagnosis_gate=true` 在同一个最终
  bundle 中被明确证明，而不是继续隐含在 relay、activate 或 rollback
  的底层 evidence 里：

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli closure-summary --db <core.db> --session-id <session-id> --documentation-file <documentation.json> --provider-smoke-file <provider-smoke.json> --require-provider-smoke --multimodal-profile-file <multimodal-profile.json> --require-multimodal-profile --regression-file <regression.json> --relay-failure-file <relay-failure.json> --hardware-compatibility-file <hardware-compatibility.json> --hardware-acceptance-matrix-file <hardware-acceptance-matrix.json> --resource-budget-governance-file <resource-budget-governance-smoke.json> --agent-excellence-file <agent-excellence-smoke.json> --release-rollback-file <release-rollback-hardening-smoke.json> --signing-provenance-file <signing-provenance-smoke.json> --observability-diagnosis-file <observability-diagnosis-smoke.json> --real-scene-e2e-file <real-scene-e2e-smoke.json> --output json > <closure-summary.json>
```

21. 以 `closure-summary.validation_gate_summary.failed_gate_ids=[]` 作为
  release-1.2.7 bundle 级别的最终证明，确认这两个独立 gate 已经在最终
  closure surface 中显式归档。

对于已提升的 release-2.2.4，最终 closure 优先使用已经打包好的
evidence-bundle 流程，而不是手工重新拼接最终 closure 命令：

22. 先运行带显式归档目录的 packaged closure smoke：

```bash
cd /home/emb/project/zephyrproject/applocation/NeuroLink
source /home/emb/project/zephyrproject/.venv/bin/activate
PYTHONPATH=. python -m neurolink_core.cli release-2.2.4-closure-smoke \
  --evidence-dir smoke-evidence/release-2.2.4-promotion-<timestamp>
```

23. 将该命令的 stdout 视为 promotion summary，并把导出的 evidence
  目录归档为 canonical release-2.2.4 bundle。当前命令至少会写出：

   1. `closure-summary.json`
   2. `coding-agent-route.json`
   3. `agent-excellence-smoke.json`
   4. `real-scene-e2e.json`
   5. `documentation-closure.json`

24. 在提升 release identity 前，确认 stdout summary 中
  `ok=true`、`closure_summary.validation_gate_summary.ok=true`、
  `closure_summary.validation_gate_summary.passed_count=30`，且
  `closure_summary.validation_gate_summary.failed_gate_ids=[]`。

25. 只有在 packaged bundle 已全绿后，才把导出的
  `closure-summary.json` 作为主 promotion artifact，并同步更新
  `neuro_cli/src/neuro_cli.py`、`neuro_cli/src/neuro_workflow_catalog.py`
  与 `subprojects/neuro_unit_app/src/main.c` 等 canonical release identity
  文件。
