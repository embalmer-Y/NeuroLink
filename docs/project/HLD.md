# NeuroLink High-Level Design

## 1. Overview

NeuroLink 是一套面向 AI 物联网自进化网络的分布式系统框架，目标是将具备较强计算与模型执行能力的 AI Core 与面向现场执行和感知的 Unit 组织为统一、可扩展、可演进的智能网络。

系统由两类节点组成：

- `AI Core`：运行多模态感性 Agent、按需理性 Agent、策略与治理逻辑、数据与记忆服务，承担用户交互、编排、跨节点访问、任务执行与审计职责。
- `Unit`：通常为基于 Zephyr RTOS 的 MCU 控制节点，挂载执行机构、传感器或局部网关能力，承担动作执行、状态采集、消息转发和动态应用承载职责。

NeuroLink 的核心设计目标不是把所有能力都堆叠在单一节点上，而是建立一个可以跨操作系统、跨网络、跨物理位置协同运行的智能控制网络，使 AI 能力可以以“编排 + 策略 + 记忆 + 执行”的方式持续演进。

本设计为高层设计（HLD），聚焦以下内容：

- 系统职责边界与逻辑分层
- Core 与 Unit 的高层架构
- 多 Core、多 Unit 的网络模型
- 控制、状态、事件、更新的高层语义
- 动态应用管理与生命周期框架
- 安全、治理、仲裁、审计、回滚等横切能力
- AI Core 的 Agent 编排框架与记忆层选型
- 与现有低层设计和代码资产的映射关系

本设计不包含线协议细节、字段级消息定义、错误码枚举、具体 API 函数签名等内容，这些由低层设计（LLD）进一步展开。

## 2. Goals and Non-Goals

### 2.1 Goals

NeuroLink 需要支持以下目标：

1. 构建由多个 AI Core 与多个 Unit 组成的智能感知与控制网络。
2. 允许 AI Core 在不同 OS 上运行，只要求具备网络访问能力、Rust/C 构建能力以及 Python 脚本执行能力。
3. 在 Core 内承载一个面向用户的多模态感性 Agent 和一个按需调用的理性 Agent，并支持本地模型与远端模型 API 的混合调用。
4. 明确用户输入和输出都由感性 Agent 独占，理性 Agent 只作为被委派的推理与执行子系统存在。
5. 允许感性 Agent 根据上下文、策略和人格目标决定是否调用理性 Agent，以及是否向用户完整转述理性 Agent 的结果。
6. 在不改变感性 Agent 上层 workflow 的前提下，允许 AI Core 以配置方式动态切换多模态模型与推理服务后端。
7. 允许 Core 直接控制本地直连 Unit，也允许经网络访问其他 Core 管辖下的远端 Unit。
8. 允许 Core 作为 Core 间消息网关与中继节点。
9. 允许一个 Unit 同时被多个 Agent 或多个 Core 访问，并通过策略与租约机制完成治理，而不是强制单主控。
10. 让 Unit 支持动态应用加载、更新、停用、回滚与生命周期管理。
11. 让 AI Core 具备实时构建 Unit App、生成可部署产物并实时部署到目标 Unit 的能力。
12. 让 Unit 数据先进入 AI Core 数据服务并落库，再以数据库更新事件通知感性 Agent。
13. 让系统具备身份认证、授权、签名更新、隔离、审计、观测与故障恢复能力。

### 2.2 Non-Goals

本阶段不解决以下问题：

1. 不定义最终线级消息编码格式。当前推荐 JSON 优先、CBOR 预留，但具体落地由 LLD 决定。
2. 不定义完整 UI、运营后台或人机界面产品形态。
3. 不规定具体 LLM 厂商或特定云服务商。
4. 不引入已废弃的 EmberMesh 设计作为正式方案。
5. 不在 HLD 中给出底层线程调度、锁策略、内存布局或协议字段级实现。
6. 当前阶段不设计正式世界模型。现有世界模型设想尚不成熟，明确延后。

## 3. Terminology

- `AI Core`：具备网络、模型执行、策略决策、代码执行、数据持久化与 Agent 编排能力的高能力节点。
- `Unit`：挂载执行机构、传感器、边缘 I/O 或局部转发能力的现场节点。
- `Affective Agent`：面向用户的多模态感性 Agent，负责理解输入、生成输出、风格控制、上下文仲裁与对理性 Agent 的委派决策。
- `Rational Agent`：按需激活的理性 Agent，负责目标分解、任务规划、复杂推理、工具调用和执行编排。
- `Capability Domain`：单个 Agent 或组件拥有的一组工具、技能、数据源和操作权限边界。
- `Control Lease`：对 Unit 或其资源的时效性控制权租约。
- `App`：在 Unit 内动态加载运行的扩展应用，承载特定业务逻辑或设备能力。
- `Gateway Unit`：除执行与采集外，还承担转发、桥接或上行接入能力的 Unit。
- `Core Data Service`：AI Core 内负责接收 Unit 数据、持久化、索引、发布数据库更新事件的统一数据服务。
- `Session Memory`：面向当前对话、当前运行或当前任务的短期记忆。
- `Long-Term Memory`：跨会话保存的用户偏好、人格关系、环境事实、历史决策与经验摘要。

## 4. Design Principles

### 4.1 User-Facing Affective Agent

用户输入必须先进入感性 Agent，用户可见输出也必须由感性 Agent 统一生成。理性 Agent 不直接面向用户暴露。

### 4.2 Rational Agent on Demand

理性 Agent 不持续订阅环境数据，不维持常驻环境副本。只有在感性 Agent 发起委派时，理性 Agent 才读取执行所需的上下文、数据和工具结果。

### 4.3 Control/Data Separation

NeuroLink 将控制语义、状态读取、事件通知和应用更新视为不同平面：

- 控制面：面向命令、编排和策略执行。
- 状态面：面向快照读取、同步和一致性检查。
- 事件面：面向异步状态变化、告警与遥测事件。
- 更新面：面向应用包、配置、策略和模型相关产物的发布、校验和激活。

### 4.4 Data Before Reasoning

Unit 数据应先进入 AI Core 数据服务并落库，再由数据库更新事件驱动感性 Agent 感知变化。理性 Agent 仅在工作时从数据库或查询接口拉取所需环境数据。

### 4.5 Capability Isolation by Default

感性 Agent 与理性 Agent 均支持 MCP 与 Skills，但默认能力域不共享。任何跨 Agent 工具、状态或凭据访问都必须通过策略层授权。

### 4.6 Evolvability First

Unit 必须以动态应用管理为基本能力，而非后续增强项。新能力优先通过 App 形式增量交付，而不是频繁整体刷写固件。

### 4.7 Policy Before Reachability

一个节点“能访问”不代表“有权控制”。所有跨 Core、跨 Agent、跨 Unit 的访问都必须受身份、策略、租约和审计约束。

### 4.8 Auditable Internal Truth

感性 Agent 可以决定是否向用户完整披露理性 Agent 的推理结论，但 AI Core 内部必须保留真实环境状态、执行结果、理性输出和审计链，不能因为对用户的呈现策略而污染内部事实。

## 5. System Context

### 5.1 AI Core Baseline Requirements

AI Core 可以运行在 Linux、Windows、macOS 或其他具备等效能力的系统上，但最低要求如下：

1. 具备稳定网络访问能力，例如 Wi-Fi、Ethernet、蜂窝网络或其他 IP 能力。
2. 可调用远端 LLM API，或本地运行一个或多个模型。
3. 感性 Agent 必须可接入多模态大模型。
4. 可编译并运行本机可执行的 Rust 与 C 代码。
5. 可运行 Python 脚本，用于工具链、自动化、Agent 编排和记忆服务集成。
6. 可持有并运行本地 MCP client/server、Skills 和扩展工具链。
7. 可针对目标 Unit 的板卡、架构、能力集和策略约束实时构建 App 产物，并发起部署。

### 5.2 Unit Baseline Requirements

Unit 主要面向 MCU 场景，基于 Zephyr RTOS 构建，最低要求如下：

1. 能通过 zenoh-pico 支持的至少一种链路接入任一 AI Core。
2. 能提供设备生命周期、状态读取、消息收发和基础策略执行能力。
3. 能承载动态应用管理框架，至少在支持 LLEXT 的架构上提供动态扩展能力。
4. 能挂载传感器、执行机构、I/O 扩展器或局部总线外设。
5. 在需要时可承担网关、协议桥接或转发角色。

### 5.3 Current Technology Baseline

本项目当前高层设计基线如下：

1. Core-Unit 控制面统一建立在 zenoh/zenoh-pico 语义上。
2. Unit 内动态应用管理基于 Zephyr LLEXT 与现有 `app_runtime_llext` 能力。
3. Unit 控制面已有低层设计基线，见 `NeuroLink/LLD.md`。
4. 已废弃的 EmberMesh 不再纳入当前设计。
5. phase2 默认更新链路已经从 HTTP 切换为 Zenoh query/reply 分块分发 `.llext`，HTTP 仅保留为兼容回退。
6. 当前 `demo_unit` 已在实板上验证 `prepare -> verify -> activate -> query apps` 与 `app-stop -> app-start` 两条闭环。
7. 当前内存观测以 `sys_heap_runtime_stats_get()` 与线程 stack watermark 为可信依据，Espressif `heap_caps_*` 在该 Zephyr target 下不作为结论来源。
8. AI Core Agent 编排框架选型确定为 `Microsoft Agent Framework`。
9. release 1.2.1 起，AI Core 的当前原生 Agent 实现以 Microsoft Agent Framework
  Python 运行时为主路径：`Agent` 承担感性/理性推理节点，Workflow 承担
  感知、落库、委派、工具执行、策略审计等确定性编排。

## 6. High-Level Architecture

### 6.1 Logical View

```text
Human / External Systems
          |
          v
 Multi-modal Interface Layer
          |
          v
 +---------------------------------------------------+
 |                     AI Core                       |
 |---------------------------------------------------|
 | User-Facing Multimodal Affective Agent            |
 |   |                                               |
 |   +--> Delegation Gate --> Rational Agent         |
 |   |                          |                    |
 |   |                          v                    |
 |   +<----- Result Filter / Release Policy ---------+
 |---------------------------------------------------|
 | Microsoft Agent Framework Workflow / Executors    |
 | Policy / Identity / Audit / Orchestrator          |
 | MCP / Skills / Tool Sandbox / Code Runner         |
 | Core Data Service / DB / Notification Bus         |
 | Session Memory / Long-Term Memory Integration     |
 | Core Messaging / Topology / Gateway               |
 +---------------------------------------------------+
          |
          | zenoh / zenoh-pico session fabric
          v
 +------------------+   +------------------+   +------------------+
 |      Unit A      |   |      Unit B      |   |   Gateway Unit   |
 | App Runtime      |   | App Runtime      |   | App Runtime      |
 | Sensors/Actuator |   | Sensors/Actuator |   | Forward/Relay    |
 +------------------+   +------------------+   +------------------+
```

### 6.2 Deployment View

NeuroLink 支持如下部署形态：

1. 单 Core + 多 Unit：最小可用部署，适合单站点或实验室环境。
2. 多 Core + 多 Unit：多个 Core 之间共享消息与状态，但各自可拥有独立管理域。
3. Core Federation：多个 Core 通过统一消息平面、身份信任和策略同步协作。
4. Unit Relay Access：部分 Unit 不直接面向公网或主 Core，而是经中间 Unit 或本地边缘节点转发接入。
5. Hybrid Edge-Cloud：部分 Core 运行在本地工业主机，部分 Core 运行在云或数据中心。

## 7. AI Core Architecture

### 7.1 Responsibilities

AI Core 负责以下高层职责：

1. 承载一个面向用户的多模态感性 Agent 和一个按需理性 Agent。
2. 使用 Microsoft Agent Framework 作为正式的 Agent 编排和 workflow 框架。
3. 统一接入用户、工具、外部服务和上下文数据源。
4. 接收 Unit 数据、持久化到数据库，并以数据库更新事件驱动感性 Agent 感知环境变化。
5. 将高层任务翻译成可治理、可审计、可执行的 Unit 控制动作。
6. 对目标 Unit App 进行实时构建、打包、签名校验前处理和部署编排。
7. 协调模型推理、工具调用、代码执行、记忆读写和策略判断。
8. 作为跨 Core 消息网关、中继节点和能力编排者。

### 7.2 Internal Subsystems

#### 7.2.1 Affective Agent

感性 Agent 是唯一用户入口和出口，负责：

1. 接收用户文本、语音、图像等多模态输入。
2. 维护交互风格、人格一致性和用户偏好。
3. 结合短期记忆与长期记忆解释当前上下文。
4. 判断当前问题是否需要理性 Agent 执行复杂推理、工具调用或实际任务。
5. 对理性 Agent 返回结果进行重排、过滤、隐藏、延迟披露或转述。
6. 将最终用户可见输出统一生成并返回。

感性 Agent 对用户的呈现不要求与内部理性结果一一对应。该能力是当前产品设定的一部分，而不是异常路径。

感性 Agent 的模型接入必须通过独立的 inference adapter 完成，而不是在 workflow、persona logic 或结果过滤逻辑中直接绑定某一具体模型 SDK。这样做的目的有三点：

1. 允许在本地模型、远端 API、不同模型家族之间切换，而不重写上层 Agent 行为。
2. 允许针对不同硬件资源预算选择不同部署档位，例如严格 16 GB 显存档位与更高能力档位。
3. 允许在不改变用户入口语义的前提下，为不同模态组合选择不同的底层模型实现。

当前推荐的感性 Agent 推理运行时分层如下：

1. `MAF Workflow Layer`
  - 负责多模态归一化、上下文注入、委派决策、结果过滤和用户输出生成。
2. `Inference Adapter Layer`
  - 负责将统一的多模态请求映射到具体模型服务，屏蔽不同模型的输入格式、鉴权、能力声明和切换细节。
3. `Model Serving Layer`
  - 默认采用 `vLLM` 提供本地多模态推理与 OpenAI-compatible 接口；必要时可切到远端兼容服务，但不改变 adapter contract。

在该结构下，`multimodal_normalization` 节点承担关键职责：

1. 将文本、图像、音频、视频统一整理为标准化输入对象。
2. 当底层模型不直接支持某种原始模态组合时，在进入模型前完成降级归一化，例如将视频拆分为关键帧与音轨摘要。
3. 维护“用户输入语义不变、模型接入格式可变”的边界。

当前 Affective Agent 的默认部署档位建议如下：

1. `Profile A: Local 16 GB Multimodal Input`
  - 目标：优先满足本地 16 GB 显存部署与动态替换。
  - 默认模型：`Gemma 3n E4B`。
  - 适用范围：文本、图像、音频输入优先；视频输入通过归一化节点拆分为关键帧与音频后进入模型。
  - 选择理由：当前代低资源导向明显，官方能力覆盖文本/图像/音频/视频输入，适合作为严格资源预算下的主路径。
2. `Profile B: Visual Agent / Video-Heavy`
  - 目标：优先提升图像、OCR、空间理解和长视频能力。
  - 默认模型：`Qwen3-VL-4B-Instruct`。
  - 适用范围：文本、图像、视频为主，音频由前置 ASR 或归一化链路补足。
  - 选择理由：当前代视觉能力强、模型尺寸更易落在本地单卡预算内，适合作为视觉优先的感性 Agent 档位。
3. `Profile C: Native Omni Output`
  - 目标：在确认必须原生语音输出后提供更完整的 omni 交互。
  - 默认模型：`Qwen3-Omni-30B-A3B`。
  - 适用范围：文本、图像、音频、视频输入与原生语音输出。
  - 风险说明：该档位不作为严格 16 GB 本地默认方案，通常需要更激进的量化、更小上下文或更高硬件预算。

在当前阶段，Affective Agent 的正式默认路径是 `Profile A`。这意味着系统优先保证“多模态输入 + 文本输出 + 本地 16 GB 可落地 + 模型可热替换”，而不是一开始就把原生语音输出作为强制门槛。

#### 7.2.2 Rational Agent

理性 Agent 负责目标分解、规划、策略生成、任务编排、约束检查和结果评估。其典型输入包括：

- 感性 Agent 委派下来的任务目标
- 当前网络拓扑
- 按需加载的 Unit 能力与状态
- 历史执行记录
- 外部工具结果
- 当前执行窗口内读取到的环境数据

其典型输出包括：

- 控制计划
- Unit 选择与编排决策
- Unit App 实时构建与部署计划
- App 部署/更新计划
- 故障处置计划
- 结构化执行结果和审计记录

理性 Agent 不直接向用户说话，也不维护独立常驻环境订阅。

#### 7.2.3 Microsoft Agent Framework Workflow Layer

AI Core 的正式 Agent 编排层采用 Microsoft Agent Framework，原因如下：

1. 官方定位为 AutoGen 的继任框架，适合新项目长期演进。
2. 提供 graph-based workflow、executor、middleware、checkpointing、human-in-the-loop、observability。
3. 支持 MCP 和多提供商模型接入，适合本项目的工具编排与多模态接入需求。

在 NeuroLink 中，MAF 的使用边界进一步明确为：

1. `Agent` 用于开放式推理节点，例如感性 Agent 的语义仲裁、呈现策略和
  理性 Agent 的计划生成。
2. `Workflow` 用于确定性流程，例如事件摄取、数据库持久化、上下文加载、
  委派窗口、工具/Unit 执行、结果过滤、审计封存和通知分发。
3. 工具调用必须通过策略、租约和审计层治理；MAF tool 能力不能绕过
  NeuroLink 的 Unit 控制面与 Neuro CLI 兼容契约。
4. release 1.2.1 的当前实现切片继续优先采用 Python Functional Workflow，以便
  在无真实模型凭据的本地环境中验证 Core 控制流；当需要固定拓扑、类型化
  边、并行 fan-out/fan-in 或明确 checkpoint 边界时，再迁移到 graph
  WorkflowBuilder 形式。

NeuroLink 中推荐的 workflow 逻辑节点至少包括：

1. `user_ingress`
2. `multimodal_normalization`
3. `affective_arbitration`
4. `rational_delegate`
5. `tool_and_unit_execution`
6. `result_filtering`
7. `database_persistence`
8. `notification_dispatch`
9. `user_response`

#### 7.2.4 Core Data Service

Core Data Service 负责：

1. 订阅 Unit 的状态、事件和查询结果。
2. 将 Unit 数据写入数据库。
3. 对数据库更新发布通知事件。
4. 为感性 Agent 提供事件驱动的上下文更新。
5. 为理性 Agent 提供按需查询接口。
6. 保留真实环境事实和执行结果，作为审计基准。

#### 7.2.5 Memory Architecture

Microsoft Agent Framework 已提供以下记忆相关基础能力：

1. `AgentSession` 用于多轮会话上下文保持。
2. `ChatHistoryProvider` 用于对话历史存储与压缩。
3. `AIContextProvider` 用于在执行前后注入和提取上下文。
4. Session 序列化与恢复，用于跨重启继续会话。

这些能力足以构建短期会话记忆和上下文注入层，但并不等于开箱即用的长期语义记忆系统。

NeuroLink 因此采用两层记忆架构：

1. `MAF Native Memory Layer`
  - 用于短期对话历史、运行态 session、workflow state、context provider 注入。
2. `External Long-Term Memory Layer`
  - 用于跨会话用户偏好、人格关系、环境事实摘要、历史决策经验、长期检索。

当前推荐的长期记忆框架为 `Mem0`，原因如下：

1. 它是专门的 memory layer，而不是与 MAF 竞争的完整 Agent runtime。
2. 具备 user/session/agent 多层记忆模型，适合作为 NeuroLink 感性 Agent 的长期记忆后端。
3. 可以通过服务化或 SDK 方式接入，适合与 MAF 的 `AIContextProvider` 和 `ChatHistoryProvider` 配合。
4. 相比 Letta，它更适合作为 MAF 的补充组件，而不是替代 MAF。
5. 相比 LlamaIndex，它更像长期记忆系统，而不是偏文档检索和 RAG 的通用数据框架。

本轮也额外评估了 `M-FLOW`。从公开项目材料看，它更像以 `Cone Graph`、graph-routed retrieval 和 episodic/procedural memory 为核心的 cognitive memory engine，在图结构情景记忆和多跳语义关联上很有潜力；但它当前仍处于 `Beta` 阶段，且集成通常需要更重的图存储/检索基础设施。

对 NeuroLink 当前阶段而言，长期记忆层的首要目标是为感性 Agent 提供稳定的跨会话偏好、关系和行为摘要，而不是优先引入更复杂的图记忆执行面。因此 `M-FLOW` 现阶段不作为默认长期记忆后端，保留为未来在图原生 episodic memory 或复杂语义联想成为核心需求时的实验候选。

不建议将 Letta 作为本项目的主记忆层，因为 Letta 更接近“自带状态与记忆的 Agent 平台”，会和 MAF 的主编排职责重叠。

不建议将 LlamaIndex 作为主记忆层，因为 LlamaIndex 更适合作为文档检索和知识接入层，而不是长期人格和关系记忆层。

#### 7.2.6 Tooling and Execution Layer

AI Core 必须提供：

1. MCP 客户端与服务端能力。
2. Skills 运行机制。
3. Rust/C 构建与执行能力。
4. Python 脚本执行能力。
5. 面向 Unit 的实时构建流水线，能够依据目标板卡、目标架构、App manifest 和策略约束生成可部署产物。
6. 面向 Unit 的实时部署流水线，能够完成产物分发、激活、验证和失败回滚触发。
7. 外部 API、数据库、文件系统和自动化工具接入能力。

该层必须以沙箱、凭据隔离、最小权限和审计为基础，而不是向所有 Agent 无条件暴露系统能力。

#### 7.2.7 Unit App Build and Deploy Orchestrator

AI Core 内需要有专门的 Unit App 构建与部署编排层，负责：

1. 根据目标 Unit 的板卡、CPU 架构、连接方式、资源预算和能力域选择正确构建配置。
2. 调用 Rust/C/Python 工具链实时生成目标 Unit 可加载或可安装的 App 产物。
3. 结合 manifest、签名策略和版本策略对构建结果进行准入检查。
4. 将构建结果实时发布到目标 Unit 或其上游中继节点。
5. 监控部署过程中的加载、初始化、激活、健康检查和回滚状态。

### 7.3 Core-to-Core Federation

多个 AI Core 之间形成松耦合联邦关系，核心能力包括：

1. 拓扑同步：交换可达节点、管理域与能力摘要。
2. 路由中继：允许某个 Core 作为其他 Core 的消息转发和访问桥。
3. 代理委托：当本 Core 无法直接执行时，将计划委托给具备权限和拓扑可达性的其他 Core。
4. 策略协同：在联邦范围内同步最小必要的身份、租约和审计元数据。

NeuroLink 不要求所有 Core 共享完整内部状态，仅要求在任务执行与治理所需的边界上建立互信与联通。

## 8. Unit Architecture

### 8.1 Responsibilities

Unit 负责以下职责：

1. 承载执行机构与传感器。
2. 与 Core 建立 zenoh-pico 会话并对外暴露控制、查询和事件能力。
3. 管理动态应用的加载、启动、暂停、停止、卸载和更新。
4. 维护本地设备状态与可观测版本信息。
5. 在需要时承担转发、桥接或上行接入角色。
6. 在访问策略约束下允许外部读写。

### 8.2 Unit Internal Layers

#### 8.2.1 Connectivity Layer

负责通过 zenoh-pico 支持的链路接入 Core，架构上不限定具体物理介质。当前可接受的接入形态包括但不限于：

- Wi-Fi
- Ethernet
- Thread
- Serial
- 其他 zenoh-pico 支持的传输方式

#### 8.2.2 NeuroLink Control Plane

Unit 控制面沿用现有 LLD 的方向：

- `Command`：处理外部下发的有副作用控制请求。
- `Query`：处理状态读取与能力查询。
- `Event`：主动发布状态变化、故障和生命周期事件。

当前已验证的最小控制面能力包括：

- `Command`：`lease acquire/release`、`app start/stop`、`app-defined dynamic commands`
- `Query`：`device`、`apps`、`leases`
- `Event`：`state`、`update`、`lease/<lease-id>`
- `Update`：`prepare`、`verify`、`activate`

#### 8.2.3 State Registry

每个 Unit 必须维护本地统一状态注册表，至少包含：

1. `node_id`
2. 固件版本与运行配置摘要
3. 已安装 App 和运行状态
4. 传感器与执行器状态
5. 健康状态和最近异常
6. 单调递增的状态版本号

#### 8.2.4 App Runtime Layer

Unit 的应用生命周期管理正式建立在现有 LLEXT runtime 模型之上。高层状态机包括：

- `UNLOADED`
- `LOADED`
- `INITIALIZED`
- `RUNNING`
- `SUSPENDED`

#### 8.2.5 Gateway/Forward Layer

部分 Unit 可以具备网关或转发能力，用于：

1. 为其他受限 Unit 提供接入桥。
2. 在现场网络与上行网络之间做转发或协议封装。
3. 承担局部消息缓冲、重试和链路恢复。

### 8.3 LLEXT Support Boundary

Zephyr LLEXT 当前受目标架构支持限制，仅在支持的 CPU 架构上提供完整动态扩展能力。因此 HLD 将 Unit 分为两类：

1. `Extensible Unit`：目标架构支持 LLEXT，可完整启用动态 App 管理。
2. `Restricted Unit`：目标架构不支持或资源不足，不启用完整动态扩展，仅保留固定功能集或受限脚本/配置更新能力。

## 9. Network and Communication Model

### 9.1 Unified Session Fabric

NeuroLink 使用 zenoh/zenoh-pico 形成统一会话平面。HLD 层面采用以下约束：

1. Core 与 Unit 的控制、查询、事件、更新均运行在统一消息语义之上。
2. Unit 可直接连 Core，也可通过其他中继节点接入。
3. 同一 Unit 不要求与 Core 处于同一二层网络、同一子网或同一物理地点。
4. 多 Core 之间可以交换路由、上下文和委托请求，但必须受策略控制。

### 9.2 Unit Attachment Modes

Unit 支持以下挂载模式：

1. `Direct Attach`：直接连接到某个 Core。
2. `Multi-Core Visible`：通过策略授权后，能被多个 Core 发现并访问。
3. `Relayed Attach`：经由中间 Unit 或边缘节点转发接入。
4. `Federated Access`：主控 Core 管辖该 Unit，但其他 Core 可经联邦网关访问其子资源。

### 9.3 Control Domains

一个 Unit 可以同时被多个 Agent 控制，但控制不是无约束共享，而是通过以下机制治理：

1. 资源级租约。
2. 操作级权限。
3. 冲突仲裁。
4. 时间窗与会话边界。
5. 审计与撤销。

## 10. Agent Collaboration Model

### 10.1 Collaboration Flow

典型协作过程如下：

1. 用户或外部系统发出任务。
2. 感性 Agent 接收多模态输入并结合 session memory、long-term memory、当前环境通知理解语境。
3. 感性 Agent 判断是否需要调用理性 Agent。
4. 若不需要，则感性 Agent 直接生成对用户的响应。
5. 若需要，则 workflow 激活理性 Agent，并按需读取数据库中的环境数据、历史执行记录和工具上下文。
6. 理性 Agent 生成控制或编排计划。
7. Policy 层判定是否允许执行。
8. Orchestrator 将计划下发到一个或多个 Unit。
9. Unit 返回结果与事件，Core Data Service 更新数据库和审计记录。
10. 数据库更新事件通知感性 Agent。
11. 感性 Agent 决定是否、何时、以何种方式向用户呈现理性结果。

### 10.2 Capability Isolation

感性 Agent 与理性 Agent 都支持 MCP 与 Skills，但默认不共享：

1. 工具注册表分离。
2. 凭据与秘密分离。
3. 可见数据源分离。
4. 可执行动作域分离。
5. 审计日志分离。

## 11. Memory and Data Architecture

### 11.1 Memory Scopes

NeuroLink 在 AI Core 内区分四类记忆：

1. `Interaction Memory`
  - 当前一次用户输入和即时多模态上下文。
2. `Session Memory`
  - 当前会话、当前 workflow、当前执行链的上下文。
3. `Long-Term User Memory`
  - 用户偏好、人格关系、长期行为模式、历史交互摘要。
4. `Operational Memory`
  - 环境事实摘要、历史执行结果、故障经验、策略触发历史。

### 11.2 MAF Memory Support Boundary

Microsoft Agent Framework 当前已提供：

1. `AgentSession`
2. `ChatHistoryProvider`
3. `AIContextProvider`
4. Session 序列化与恢复
5. 对话历史裁剪与压缩入口

这些能力适合承担：

1. 会话历史
2. 多轮对话状态
3. 运行期 context injection
4. workflow / executor state

这些能力尚不足以直接覆盖：

1. 长期语义记忆存储与检索
2. 跨用户、跨设备、跨时间的个性化记忆管理
3. 记忆抽取、压缩、评分和生命周期治理
4. 环境事实摘要与用户记忆的统一检索策略

### 11.3 Recommended External Memory Layer

NeuroLink 推荐采用 `Mem0` 作为 MAF 之外的长期记忆层。

推荐理由：

1. 它是独立 memory layer，和 MAF 的职责边界清晰。
2. 它更适合作为当前阶段的生产型 sidecar memory service，而不改变 AI Core 的主编排模型。
3. 相比 `M-FLOW`，它在当前方案下部署更轻，适合先满足感性 Agent 的长期偏好和关系记忆需求。
4. `M-FLOW` 已被评估，但由于仍是 Beta 且更偏图原生 cognitive memory engine，暂不作为当前默认方案。
2. 对 user、session、agent 多层记忆有直接建模能力。
3. 它更适合“感性 Agent 的长期人格与关系记忆”这类场景。
4. 可通过自定义 `AIContextProvider` 与 `ChatHistoryProvider` 接入，不要求替换主 workflow 框架。
5. 相比 Letta，更少引入二次 Agent runtime 竞争。
6. 相比 LlamaIndex，更贴近长期记忆，而不是主要面向文档检索。

### 11.4 Database Role

数据库不是长期人格记忆层的替代，而是事实源和操作源，主要承担：

1. Unit 遥测和状态落库
2. 状态版本化
3. 执行记录和审计记录保存
4. 理性 Agent 的按需环境查询
5. 感性 Agent 的事件通知触发

## 12. Application Lifecycle and Update Model

### 12.1 Lifecycle Framework

Unit 必须提供应用生命周期管理框架，正式能力包括：

1. 下载或接收应用包。
2. 校验签名与 manifest。
3. 安装与加载。
4. 初始化与启动。
5. 挂起与恢复。
6. 停止与卸载。
7. 版本切换与回滚。

### 12.2 Update Pipeline

推荐的高层更新流程如下：

1. Core 侧选择目标 Unit、目标 App 版本或目标功能变更。
2. Core 根据目标 Unit 的板卡、架构、运行时能力和策略约束实时构建 App 产物。
3. Core 生成或收集 manifest、签名材料和部署元数据。
4. Unit 或上游节点获取应用包及 manifest。
5. 验证签名、版本兼容性、能力声明和资源预算。
6. 在不破坏现网稳定性的前提下装载新版本。
7. 进入灰度或试运行阶段。
8. 通过健康检查与策略校验后激活。
9. 失败则回滚到上一个稳定版本。

## 13. Messaging and API Framework

### 13.1 Unit Messaging Responsibilities

Unit 消息管理框架至少需要支持：

1. 回调注册与触发。
2. 远程传感器读取 API。
3. 远程控制 API。
4. 事件发布与状态通知。
5. 在策略约束下被外部节点读写。

### 13.2 API Exposure Principles

远程 API 不是裸露寄存器或驱动入口，而是受治理的能力接口。对外暴露应遵循以下原则：

1. 能力优先，不暴露无边界内部实现。
2. 面向对象资源，而不是面向任意内存地址。
3. 每个读写操作都可绑定访问策略。
4. 每次变更都能被审计。

## 14. Security, Governance and Arbitration

### 14.1 Identity and Trust

NeuroLink 需要统一身份与信任体系，至少包括：

1. Core 身份
2. Unit 身份
3. Agent 身份
4. App 发布者身份
5. 工具与服务身份

### 14.2 Authorization Model

授权必须至少覆盖以下维度：

1. 谁可以发现某个 Unit。
2. 谁可以读取某类状态。
3. 谁可以控制某个执行器。
4. 谁可以安装或更新某类 App。
5. 谁可以借由某个 Core 访问远端 Unit。

### 14.3 Arbitration Model

为满足“一个 Unit 可被多个 Agent 同时控制”的需求，HLD 采用租约制仲裁模型：

1. 每个可冲突资源都可以发放控制租约。
2. 租约有 TTL、续约和撤销机制。
3. 不同操作类型可以有不同优先级和抢占规则。
4. 无租约操作只能执行只读或受限动作。
5. 紧急策略可触发强制回收或降级模式。

### 14.4 Presentation vs Internal Truth

当前产品设定允许感性 Agent 对用户进行策略性隐藏、转述、延迟披露，甚至在表现层做非完整事实呈现。

但必须满足以下硬约束：

1. 真实环境状态必须保存在 Core Data Service 和数据库中。
2. 理性 Agent 原始输出必须进入审计记录。
3. 实际下发到 Unit 的命令必须可追溯。
4. 面向用户的表述策略不能污染内部事实源。

### 14.5 Signing, Audit and Rollback

以下能力视为核心能力，不作为未来增强项：

1. App 包签名校验。
2. manifest 与版本的绑定校验。
3. 操作审计日志。
4. 更新失败回滚。
5. 敏感控制操作的因果链记录。

## 15. Observability and Operations

### 15.1 Topology and Health

系统需要持续感知以下信息：

1. Core 与 Unit 的在线状态。
2. Unit 当前挂载关系。
3. 关键链路质量与会话状态。
4. App 运行状态、异常和健康分级。
5. 传感器、执行器和网关节点的健康状态。

### 15.2 Versioned State

每个 Unit 的核心状态必须可版本化，Core 端维护聚合视图时也应保留版本语义，用于：

1. 去重与顺序判断。
2. 事件与快照一致性检查。
3. 异常恢复后的重新同步。
4. 执行结果溯源。

### 15.3 Operations Surface

NeuroLink 运维面建议至少覆盖：

1. 节点发现与注册
2. 配置分发
3. 策略下发
4. 实时构建任务编排、产物追踪与部署控制
5. 应用部署与版本治理
6. 日志、事件和告警聚合
7. 故障诊断和回滚触发
8. 记忆读写、记忆审计和记忆清理治理

## 16. Framework Selection Summary

### 16.1 Agent Framework Decision

NeuroLink 正式选择 `Microsoft Agent Framework` 作为项目的 Agent 框架。

原因如下：

1. 它是微软官方面向新项目推荐的框架，并作为 AutoGen 的继任方向。
2. 它的 workflow / executor 模型适合本项目的“感性 Agent 仲裁 -> 理性 Agent 委派”结构。
3. 它具备 middleware、checkpoint、observability、MCP 集成等工程化能力。

### 16.2 Memory Framework Decision

NeuroLink 的长期记忆层推荐采用 `Mem0`，并通过 MAF 的 `AIContextProvider` / `ChatHistoryProvider` 接入。

`M-FLOW` 已纳入对比。它在 graph-native episodic memory 与 graph-routed retrieval 方面具有潜力，但当前成熟度与运维复杂度不适合作为本阶段默认选型。

若未来需要增强文档检索与知识库访问，可再引入 LlamaIndex 作为 retrieval / indexing 层，但它不是当前首选记忆系统。

### 16.3 Model Serving Decision

NeuroLink 的感性 Agent 模型服务层正式建议采用 `vLLM` 作为默认本地推理运行时。

原因如下：

1. 当前文档与模型支持矩阵已覆盖 `Gemma 3n`、`Qwen3-VL`、`Qwen3-Omni`、`Phi-4-multimodal` 等当前候选家族。
2. 提供 `OpenAI-compatible` 的 chat、responses、transcription、realtime 等接口，适合作为上层 adapter 的稳定目标。
3. 支持多模态输入、量化、LoRA、模型加载参数控制与统一服务化部署，适合“同一上层 workflow，下层替换不同模型”的架构目标。
4. 相比只面向简单视觉用例的轻量运行时，它更适合作为 NeuroLink 的长期主服务层。

`Ollama` 可作为快速验证或简单 image-plus-text 场景的次选，但不作为当前正式主路径。`SGLang` 在本轮实现中不作为默认选项，因为还缺少足够直接、稳定的验证证据支撑当前架构决策。

### 16.4 Current Affective Model Profiles

当前正式建议的模型分层如下：

1. `Primary Local Profile`
  - `Gemma 3n E4B`
  - 目标：严格 16 GB 本地部署、多模态输入、动态替换优先。
2. `Visual-Heavy Profile`
  - `Qwen3-VL-4B-Instruct`
  - 目标：视觉理解、OCR、视频与 visual agent 能力优先。
3. `Omni Premium Profile`
  - `Qwen3-Omni-30B-A3B`
  - 目标：当原生语音输出成为硬需求时启用。

`Gemma 4 E4B` 是值得持续跟踪的当前代候选，尤其在官方能力说明和显存规划上表现很强；但在本轮实现中，默认主路径仍优先选取当前已更直接纳入现有 vLLM 多模态支持矩阵、且更适合立即落地的 `Gemma 3n E4B`。

## 17. Reference Implementation Mapping

### 17.1 Existing Assets Reused

当前代码库中以下资产可直接作为实现基线：

1. `NeuroLink/LLD.md`
2. `app_runtime_llext`
3. Zephyr LLEXT

### 17.2 HLD to LLD Boundary

以下内容属于 HLD 固化决策：

1. Core 与 Unit 的职责边界。
2. 感性 Agent 独占用户交互，理性 Agent 按需被委派。
3. Microsoft Agent Framework 作为 Core 侧 Agent 编排框架。
4. MAF native memory + Mem0 long-term memory 的双层记忆架构。
5. 多 Core、多 Unit 的组网与联邦模型。
6. 租约制控制仲裁。
7. 动态应用管理作为 Unit 核心能力。
8. 安全、审计、签名和回滚是核心横切能力。

以下内容属于 LLD 深化内容：

1. 资源命名规则。
2. 报文 schema。
3. 错误码与异常映射。
4. 回调注册接口。
5. 具体 manifest 字段与 ABI 兼容规则。
6. 连接重试、缓存、QoS 和内存优化细节。
7. MAF workflow/executor 的具体状态定义与事件流。
8. Mem0 接入的索引结构、抽取策略和清理策略。

## 18. Constraints and Risks

### 18.1 Technical Constraints

1. Unit 动态应用管理依赖 LLEXT 支持的目标架构。
2. MCU 资源有限，zenoh-pico 需要根据设备内存调整缓冲区与分片参数。
3. 实时构建与实时部署会引入额外的工具链、产物缓存、签名和目标适配复杂度。
4. 多 Agent 并发控制会显著增加策略和状态一致性复杂度。
5. 多模态感性 Agent 和长期记忆层会显著提高 Core 侧资源与治理复杂度。

### 18.2 Primary Risks

1. 若不尽早固化租约与授权模型，多控制者场景会快速失控。
2. 若实时构建流水线与目标 Unit 适配模型不稳定，部署成功率和产物可信度会快速下降。
3. 若 App 签名与回滚链路后置，动态更新将成为主要风险源。
4. 若感性 Agent 的对外呈现策略没有内部审计边界，会破坏系统可信性。
5. 若忽略长期记忆治理，感性 Agent 的人格与偏好会出现漂移、污染和误召回。

## 19. Roadmap Recommendations

### 19.1 Phase 1

1. 固化 HLD 与 Unit 控制面 LLD 的分层边界。
2. 完成单 Core + 多 Unit 的最小闭环。
3. 基于现有 runtime 打通 App 生命周期、状态查询、事件上报与最小部署闭环。
4. 建立基础身份、策略、审计与签名链路。
5. 建立最小可用的实时构建与实时部署链路。
6. 基于 MAF 建立感性 Agent 主 workflow 与理性 Agent 委派框架。

### 19.2 Phase 2

1. 建立多 Core 联邦与跨 Core 访问远端 Unit 的能力。
2. 引入租约制控制仲裁。
3. 建立 Gateway Unit 角色与转发能力。
4. 接入 Mem0 长期记忆层。
5. 建立感性 Agent 的记忆治理、召回和过滤策略。
6. 建立多板卡、多架构 Unit App 构建矩阵与部署策略。

### 19.3 Phase 3

1. 建立标准化 App 发布、灰度、回滚和资源预算治理。
2. 完善多 Agent 协同、策略冲突自动化检查和全网运维面。
3. 建立实时构建缓存、增量发布和跨 Core 构建委托能力。
4. 若需要，再引入更完整的知识检索层和 Restricted Unit 兼容策略。

## 20. Summary

NeuroLink 的核心不是单个智能节点，而是一张由 AI Core 和 Unit 组成的、可编排、可治理、可演进的智能网络。

在这个网络中：

1. AI Core 负责用户交互、策略、协同、记忆与编排。
2. Unit 负责执行、感知、转发与边缘扩展承载。
3. 感性 Agent 是唯一面向用户的多模态 Agent。
4. 理性 Agent 是被感性 Agent 按需调用的执行与推理子系统。
5. Microsoft Agent Framework 构成 Core 侧正式 Agent 编排骨架。
6. MAF 原生会话记忆负责短期状态，Mem0 负责长期记忆层。
7. zenoh/zenoh-pico 构成统一消息与会话平面。
8. LLEXT-based App Runtime 构成 Unit 自进化能力的正式载体。
9. 安全、仲裁、签名、审计、回滚和状态版本化构成系统可控性的基础。

该 HLD 为后续 LLD、原型实现和产品化裁剪提供统一架构基线。