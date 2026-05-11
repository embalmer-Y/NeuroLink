# Release 2.2.0 QwenPaw Reference Foundation Plan

## 1. Purpose

Release 2.2.0 starts the post-2.1.0 productization train by turning the
QwenPaw source review into NeuroLink-native implementation contracts.

The goal is not to turn NeuroLink into QwenPaw or to copy QwenPaw source by
default. The goal is to learn from QwenPaw's proven extension surfaces while
preserving NeuroLink's stronger Unit, policy, lease, approval, audit, and
release-evidence boundaries.

Release 2.2.0 is therefore a foundation release. It freezes the reference
findings, contract names, small-version roadmap, and evidence gates that later
2.2.x releases must satisfy before any production QQ, WeCom, WeChat, MCP,
Skill, coding-agent, persona-growth, or long-soak behavior is promoted.

## 2. QwenPaw Reference Findings

The local QwenPaw checkout at `QwenPaw/` provides the following reference
patterns:

1. Channel abstraction and registry:
   - `src/qwenpaw/app/channels/base.py`
   - `src/qwenpaw/app/channels/registry.py`
   - useful patterns: common channel contract, content parts, session
     resolution, batching, debounce, channel discovery, and custom-channel
     loading.
2. Chinese social channel implementations:
   - `src/qwenpaw/app/channels/qq/channel.py`
   - `src/qwenpaw/app/channels/onebot/channel.py`
   - `src/qwenpaw/app/channels/wecom/channel.py`
   - `src/qwenpaw/app/channels/wechat/channel.py`
   - useful patterns: QQ official Bot WebSocket plus HTTP reply, OneBot v11
     reverse WebSocket for NapCat-compatible deployments, WeCom AI Bot
     WebSocket receive/reply, WeChat iLink long-polling and QR/token readiness,
     reconnect, heartbeat, dedupe, media handling, message merge, and group or
     direct session policy.
3. Provider and model management:
   - `src/qwenpaw/providers/provider_manager.py`
   - `src/qwenpaw/app/routers/providers.py`
   - `src/qwenpaw/cli/providers_cmd.py`
   - useful patterns: provider registry, base URL/API-key configuration,
     model listing/discovery, connection tests, active model slot selection,
     and masked secret display.
4. Skills, MCP, and tool governance:
   - `src/qwenpaw/agents/skills_manager.py`
   - `src/qwenpaw/app/routers/mcp.py`
   - `src/qwenpaw/agents/tool_guard_mixin.py`
   - `src/qwenpaw/security/tool_guard/models.py`
   - useful patterns: `SKILL.md` front matter, active skill routing, MCP client
     descriptors, masked env/header values, tool guard threat categories, and
     approval-oriented tool interception.
5. Coding-agent and self-improvement reference:
   - `src/qwenpaw/agents/acp/tool_adapter.py`
   - `src/qwenpaw/config/config.py`
   - useful patterns: external coding-agent runners, permission request
     formatting, runner config, command/args/env boundaries, and disabled-by-
     config extension points.
6. Persona, prompt, memory, and long-run stability:
   - `src/qwenpaw/agents/prompt.py`
   - `src/qwenpaw/agents/memory/reme_light_memory_manager.py`
   - `src/qwenpaw/app/runner/task_tracker.py`
   - useful patterns: prompt files such as `AGENTS.md`, `SOUL.md`, and
     `PROFILE.md`, memory maintenance, vector/FTS fallback, store-version
     sentinels, heartbeat, task tracking, replay buffers, and graceful wait or
     shutdown behavior.

## 3. License And Copy Boundary

QwenPaw is an external reference project. NeuroLink may use it to inform
architecture, terminology, and test planning, but release 2.2.0 does not approve
copying source files into NeuroLink.

Rules:

1. Reimplement the required patterns in NeuroLink's own modules and style.
2. Do not paste QwenPaw implementation code into NeuroLink unless the operator
   explicitly approves a license/notice review.
3. If a future release intentionally imports or copies Apache-2.0 code, the
   change must document the copied files, preserve required notices, and add a
   license-boundary evidence item before promotion.
4. NeuroLink's policy, lease, approval, audit, and closure-summary gates remain
   authoritative even when a QwenPaw pattern is adopted.

## 4. NeuroLink-Native Contracts

Release 2.2.0 reserves the following contract names for follow-up releases:

1. `SocialAdapterRegistry`
   - Discovers social adapters and their compliance metadata.
   - Keeps `SocialMessageEnvelope` as the canonical ingress shape.
   - Records adapter kind, channel kind, principal binding, rate-limit class,
     require-mention policy, allowlist policy, lab/production classification,
     and Affective-only egress capability.
2. `ProviderProfileRegistry`
   - Owns configured provider profiles, active model slots, provider readiness,
     and model discovery/test evidence.
   - Stores only secret references or env var names in evidence.
3. `SkillDescriptorRegistry`
   - Loads NeuroLink Skill descriptors with name, description, trigger words,
     references, scripts, required env/bin metadata, enabled channels, and
     approval class.
4. `McpClientDescriptor`
   - Describes governed MCP clients with `stdio`, `streamable_http`, or `sse`
     transport metadata.
   - Read-only execution may be enabled only through Core policy; side-effecting
     MCP tools remain approval-gated.
5. `CodingAgentRunnerDescriptor`
   - Describes external coding-agent runners such as Copilot CLI, qwen-code,
     opencode, or local command adapters.
   - Runners are disabled by default and must route through self-improvement,
     approval, and audit evidence.
6. `PersonaSeedConfig`
   - Captures first-run personality seed settings for the Affective persona.
   - Separates immutable seed configuration from runtime-derived
     `PersonaGrowthState`.
7. `RuntimeConfigChangeEvidence`
   - Records who changed provider, social, MCP, Skill, persona seed, or runner
     configuration, what changed, whether secrets were referenced safely, and
     whether a restart/hot reload occurred.

## 5. Small-Version Roadmap

Release 2.2.x is split into AI-assisted implementation slices:

| Release | AI estimate | Scope |
| --- | ---: | --- |
| 2.2.0 | 2 development days | QwenPaw reference baseline, license boundary, and contract freeze. |
| 2.2.1 | 2 development days | Runtime AI provider and model reconfiguration. |
| 2.2.2 | 3 development days | Social adapter registry, QQ official Bot path, and OneBot/NapCat-compatible path. |
| 2.2.3 | 3 development days plus credential wait | WeCom production path and optional WeChat iLink path. |
| 2.2.4 | 3 development days | Tool, MCP, Skills, ToolGuard-style threat taxonomy, and coding-agent delegation. |
| 2.2.5 | 3 development days | Persona seed config, growth state, and memory immutability. |
| 2.2.6 | 4 development days plus soak wall-clock | Heartbeat, task tracking, memory maintenance, self-optimization, World Model v1, and staged soak. |
| 2.3.0 | 2 development days plus final evidence | Integrated social resident promotion after 2.2.x gates are green. |

AI development estimates cover coding, focused tests, and deterministic smoke
evidence. They do not compress third-party account approval, live social API
credential readiness, or long hardware soak wall-clock time.

## 6. Release 2.2.0 Workstreams

### WS-1 Reference Review And Traceability

1. Record the QwenPaw reference surfaces listed in this plan.
2. Map each reference surface to a NeuroLink-owned module and future release.
3. Preserve the 2.1.0 promoted identity until implementation gates are green.

Exit criteria:

1. The reference plan exists in `docs/project/`.
2. The progress ledger records the start of the 2.2.0 line.
3. No NeuroLink runtime behavior changes are made in the reference slice.

### WS-2 Contract Freeze

1. Reserve contract names for social registry, provider profile registry,
   Skill descriptors, MCP descriptors, coding-agent runners, persona seed, and
   runtime config evidence.
2. Define which follow-up release owns each contract.
3. Define the evidence gates that must exist before promotion.

Exit criteria:

1. Contract names and follow-up release ownership are documented.
2. Later 2.2.x work can add code without renegotiating architecture boundaries.

### WS-3 Compliance And License Boundary

1. Classify production social paths separately from lab/community bridges.
2. Explicitly mark OneBot/NapCat-compatible QQ and WeChat iLink as paths that
   may need operator risk acceptance depending deployment context.
3. Keep QwenPaw source as reference unless license/notice review is approved.

Exit criteria:

1. `license_boundary_gate` can pass without source copying.
2. Social compliance evidence has a place in later closure summaries.

### WS-4 Evidence Planning

Release 2.2.0 reserves the following future gates:

1. `qwenpaw_reference_review_gate`
2. `runtime_config_contract_gate`
3. `license_boundary_gate`
4. `model_profile_config_gate`
5. `social_adapter_registry_gate`
6. `qq_social_gate`
7. `onebot_social_gate`
8. `wecom_social_gate`
9. `wechat_ilink_gate`
10. `social_compliance_gate`
11. `skill_registry_gate`
12. `mcp_governed_execution_gate`
13. `tool_guard_gate`
14. `coding_delegation_gate`
15. `persona_seed_gate`
16. `persona_growth_gate`
17. `memory_immutability_gate`
18. `autonomy_heartbeat_gate`
19. `long_autonomy_soak_gate`
20. `self_optimization_gate`
21. `world_model_context_gate`

Exit criteria:

1. Existing 2.1.0 gates remain inherited and must not be weakened.
2. New gates are introduced as deterministic smoke payloads before they become
   promotion blockers.

## 7. Release 2.2.1 Preview

Release 2.2.1 should implement runtime AI provider and model reconfiguration.

Required user-facing surfaces:

1. `provider-list`
2. `provider-config`
3. `provider-test`
4. `model-list`
5. `model-set-active`
6. `model-profile-smoke`

Rules:

1. Provider base URLs, model names, and active model slots may be changed by CLI
   or API without editing source code.
2. Secrets must be stored as env var names or secret references, not printed in
   evidence.
3. Missing credentials must fail closed with structured readiness metadata.
4. Affective and Rational model slots may diverge, but both remain behind Core
   policy and prompt-safe context rules.

## 8. Release 2.2.2 And 2.2.3 Preview

Release 2.2.2 owns QQ and OneBot-compatible adapters:

1. `qq_official` for the official QQ Bot path.
2. `onebot_qq` for OneBot v11 reverse WebSocket deployments.

Release 2.2.3 owns WeCom and optional WeChat iLink adapters:

1. `wecom` is the preferred production Chinese enterprise path.
2. `wechat_ilink` is optional or lab-scoped unless compliance and account risk
   are explicitly approved.

All social adapters must preserve:

1. identity-bound ingress;
2. persisted Core events before reasoning;
3. group/private/mention/allowlist policy;
4. rate limiting and dedupe;
5. Affective-only egress;
6. side-effect requests converted to approval records;
7. no raw Rational plans, secrets, stack traces, or internal audit payloads in
   social replies.

## 9. Release 2.2.4 Preview

Release 2.2.4 should improve Agent extensibility and programming ability.

Scope:

1. Skill descriptor registry inspired by `SKILL.md`, but governed by NeuroLink
   policy and evidence.
2. Governed MCP client descriptors with masked env/header metadata.
3. Read-only MCP execution through Core policy as the first executable MCP
   increment.
4. ToolGuard-style threat categories for tool plans and arguments.
5. Coding-agent runner descriptors routed through self-improvement approval.

Non-goals:

1. No direct model-to-shell execution.
2. No side-effecting MCP or coding-agent action without approval.
3. No autonomous commit, push, firmware flash, credential mutation, or
   production deploy.

## 10. Release 2.2.5 Completion

Release 2.2.5 is now complete as the bounded persona seed, growth governance,
privacy operation, and immutability line.

Delivered bounded implementation status:

1. `neurolink_core.persona` now includes `PersonaSeedConfig`,
   `PersonaGrowthState`, runtime-evidence-only growth application, and
   immutability stamp / tamper detection helpers.
2. `neurolink_core.cli` now exposes first-class governed operator paths:
   `persona-seed-setup`, `persona-growth-apply`, `persona-state-inspect`,
   `persona-state-export`, `persona-state-delete`, and
   `persona-tamper-report`.
3. `closure-summary` now carries additive `persona_seed_gate`,
   `persona_growth_gate`, and `memory_immutability_gate` evidence from the
   persona smoke path.
4. The bounded 2.2.5 line remains deterministic and file-driven; no live
   mutable daemon or background memory rewriting path is introduced in this
   release.

Required design:

1. `PersonaSeedConfig` captures initial AI girl personality settings.
2. `PersonaGrowthState` changes only through runtime evidence: social
   interactions, Unit events, relationship summaries, Vitality, recovery, and
   approved self-improvement.
3. After first setup, manual Agent memory or growth-state rewriting is not
   allowed.
4. Privacy delete, redaction, and export remain allowed governance operations,
   but they are not arbitrary memory rewriting.
5. Tamper detection records hash/provenance mismatches and blocks promotion if
   unexplained manual edits are found.

Bounded operator evidence for this release should include:

1. `persona-seed-setup` proving a governed seed initializes persona and growth
   state together.
2. `persona-growth-apply` proving `PersonaGrowthState` revision changes only
   when runtime evidence is supplied.
3. `persona-state-inspect` proving read-only inspection and prompt-safe
   rational summaries remain available.
4. `persona-state-export` and `persona-state-delete` proving privacy export,
   redaction, and delete are supported without arbitrary growth-state rewrite.
5. `persona-tamper-report` plus `closure-summary` proving immutability and
   provenance mismatches are detectable and promotable as explicit gates.

## 11. Release 2.2.6 Preview

Release 2.2.6 should add long-run stability and self-optimization.

Scope:

1. Heartbeat and active-hour configuration for `core-daemon`.
2. Task tracking and replay buffer for long-running operations.
3. Memory maintenance with auditable consolidation and stale-context summaries.
4. Approved self-optimization apply path for low-risk changes.
5. World Model v1 for temporal incidents, Unit location/capability context, and
   prompt-safe relationship context.
6. Staged soak: 2-hour developer soak, 24-hour release-candidate soak, and
   72-hour promotion soak when hardware and social credentials are stable.

## 12. Promotion Boundary

Release 2.2.0 itself is not a product identity promotion. It starts the
QwenPaw-informed implementation line while keeping the canonical promoted
identity at 2.1.0.

Promotion to 2.3.0 is allowed only after:

1. all required 2.2.x deterministic gates pass;
2. inherited 2.1.0 26-gate closure remains green;
3. at least one production-grade Chinese social channel is live, or the release
   is explicitly classified as a foundation/RC rather than a fully promoted
   social-resident release;
4. hardware/resource/signing evidence is refreshed after any release identity
   change;
5. README, runbooks, Neuro CLI, workflow catalog, and sample Unit app identity
   are aligned only after the green promotion bundle exists.