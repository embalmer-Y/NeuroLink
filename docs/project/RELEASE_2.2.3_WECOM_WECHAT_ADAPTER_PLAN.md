# Release 2.2.3 OpenClaw-Compatible Social Gateway Plan

Status: promoted on 2026-05-11.
The release-2.2.3 implementation, documentation alignment, bounded gateway
closure, and final promotion bundle are complete. The archived promotion bundle
is `smoke-evidence/release-2.2.3-promotion-20260511T045344Z/`, whose
`closure-summary-final.json` passed 29 of 29 validation gates before release
identity moved to `2.2.3`.

Release 2.2.3 now pivots from a channel-specific WeCom/WeChat expansion into an
OpenClaw-compatible social gateway architecture. The promoted release-2.2.2
baseline remains the bounded `qq_official` / `onebot_qq` social adapter line,
while release-2.2.3 extends the social surface in two complementary ways:

1. keep `wecom` as the preferred direct enterprise path for bounded production
   evidence;
2. introduce an OpenClaw-compatible host/plugin contract as the common bridge
   for `wechat_ilink`, future `qq_openclaw`, and later compatible plugins
   without turning NeuroLink into an always-on social resident.

The goal is still bounded, operator-driven evidence rather than a long-running
social daemon. Release-2.2.3 must preserve the release-2.2.2 safety boundary:
Affective-only egress, explicit live-network allowance, masked credential and
plugin evidence, Core-owned policy and approval, no direct plugin installation,
and no raw Rational exposure.

## 1. Scope

Release 2.2.3 owns:

1. `wecom` as the preferred direct enterprise adapter path for bounded live
   evidence.
2. a shared OpenClaw host/plugin payload contract for plugin-mediated social
   ingress.
3. registry/profile metadata that distinguishes direct adapters from
   OpenClaw-hosted adapters.
4. deterministic readiness and fail-closed compliance evidence for
   `wechat_ilink` and future `qq_openclaw`-style profiles.
5. a bounded OpenClaw gateway client and additive closure-summary evidence once
   the generic contract is stable.

Release 2.2.3 does not require by default:

1. always-on social daemons or unattended resident loops;
2. direct NeuroLink-side QR login or token automation for personal-account
   plugins;
3. plugin installation or package discovery inside NeuroLink;
4. Tool/MCP/Skill registry work reserved for release-2.2.4;
5. Persona seed or growth-state work reserved for release-2.2.5;
6. long-run heartbeat, memory-maintenance, self-optimization, or World Model v1
   work reserved for release-2.2.6.

## 2. HLD / LLD Traceability

HLD alignment:

1. `Social Adapter` remains the normalization layer from external channels into
   Core ingress envelopes.
2. OpenClaw is treated as a hosted plugin transport boundary, not as a place to
   run Core policy or tool execution.
3. user-visible output remains Affective-owned.
4. Rational Agent remains delegated and internal.
5. policy, approval, and audit still outrank channel or plugin reachability.

AI Core LLD 5.13 alignment:

1. social adapters bind channel identity, permission class, transport kind, and
   readiness.
2. inbound WeCom and OpenClaw-hosted payloads normalize into the same Core
   event path used by `agent-run`, replay, and release-2.2.2 QQ ingress.
3. outbound user-visible responses remain Affective-planned and audit-visible.
4. readiness, compliance, and plugin/host metadata remain part of smoke and
   closure evidence.
5. social adapters and gateway clients never execute Rational plans, Unit
   tools, plugin installers, or shell actions directly.
6. secrets, raw plans, stack traces, and internal-only audit payloads never
   appear in social replies or release evidence.

## 3. Transport Targets

### 3.1 `wecom`

`wecom` remains the preferred production Chinese enterprise path for
release-2.2.3.

Required contract:

1. persisted adapter-profile metadata with env-var credential references only;
2. deterministic inbound sample fixtures for `group`, `direct`, and
   `group_no_mention`;
3. mention/private/group policy metadata;
4. bounded ingress validation path suitable for release evidence;
5. additive closure evidence for authenticated connection, dispatch-to-Core,
   and bounded runtime.

### 3.2 OpenClaw-hosted adapters

OpenClaw-hosted adapters cover `wechat_ilink`, future `qq_openclaw`, and later
compatible plugin-mediated platforms.

Required contract:

1. a shared payload envelope carrying host id, plugin id/package, plugin
   version, installer package, platform kind, message identity, mention list,
   compliance class, and bounded live-network evidence;
2. deterministic profile/config/readiness support even when live validation is
   deferred;
3. explicit lab or compatibility classification in smoke evidence when the path
   is not yet a promoted production route;
4. explicit compliance acknowledgement before live readiness may pass;
5. fail-closed operator metadata when host reachability, plugin metadata,
   account posture, or compliance acknowledgement is missing.

The exact QQ OpenClaw plugin package/installer coordinate remains
operator-supplied until verified. NeuroLink must not hard-code guessed package
names.

## 4. Command Surfaces

Release 2.2.3 continues to reuse the existing social adapter operator surface
and extends it with a generic bounded OpenClaw gateway path rather than adding
per-platform resident clients.

### 4.1 `social-adapter-list`

Must report direct and OpenClaw-hosted profiles with:

1. enabled state;
2. readiness state;
3. compliance class;
4. masked credential references;
5. transport kind;
6. mention or group-session policy metadata;
7. live-network allowance or missing-requirement metadata;
8. OpenClaw host/plugin metadata when applicable.

### 4.2 `social-adapter-config`

Must allow operators to configure `wecom`, `wechat_ilink`, and future
OpenClaw-hosted profiles without editing source code:

1. endpoint or gateway host reference;
2. credential env-var references only;
3. channel kinds and mention policy;
4. transport kind;
5. compliance metadata and acknowledgement state;
6. bounded live-network allowance;
7. host/plugin package metadata as evidence, not as an installer action.

### 4.3 `social-adapter-test`

Must support deterministic validation for `wecom`, `wechat_ilink`, and later
OpenClaw-hosted profiles using the same sample-scenario contract as
release-2.2.2:

1. `group`
2. `direct`
3. `group_no_mention`

The default path must remain deterministic and network-free. Bounded transport
probing or bounded ingress validation must remain explicit and must only run
when the profile is already marked ready for that class of validation.

### 4.4 `social-adapter-smoke`

Must extend the release-2.2.2 smoke payload with:

1. WeCom deterministic normalization and bounded gateway evidence;
2. OpenClaw-hosted `wechat_ilink` and `qq_openclaw` readiness and compliance
   metadata;
3. operator-facing distinction between deterministic readiness, host/plugin
   contract readiness, and bounded live transport evidence;
4. plugin-specific results that do not weaken the promoted direct QQ/WeCom
   gates.

### 4.5 Bounded Live Validation

Release 2.2.3 may add:

1. the existing bounded WeCom ingress client and closure artifact;
2. a generic bounded `openclaw-gateway-client` that receives hosted plugin
   events and routes them through the selected adapter path;
3. an additive `openclaw-gateway-closure` if the generic gateway evidence is
   fed into `closure-summary`.

These commands must remain bounded by runtime and event count, must not imply a
long-running resident, and must remain subject to the same Core/Affective-only
response boundary as the QQ and WeCom ingress paths.

## 5. Compliance Stance

### 5.1 WeCom

`wecom` is the preferred production path for release-2.2.3 when enterprise
credentials and endpoint metadata are available.

Release-2.2.3 real-scene validation should start with deterministic fixtures,
then move to bounded live validation only when the operator explicitly enables
the live path and the profile already satisfies readiness requirements.

### 5.2 OpenClaw-hosted WeChat and QQ plugin paths

`wechat_ilink` and `qq_openclaw` remain lab-scoped or compatibility-only unless
compliance, account posture, and host/plugin readiness are explicit.

`qq_openclaw` is now implemented as a separate hosted compatibility profile,
but it must remain distinct from the promoted `qq_official` official API path
until equivalent bounded evidence is green.

Weixin/OpenClaw setup stays outside NeuroLink. A currently verified external
installer example is `npx -y @tencent-weixin/openclaw-weixin-cli@latest
install`, but NeuroLink records installer/package metadata only and does not run
the installer itself.

## 6. Development Order

1. realign the release-2.2.3 plan, README, and progress ledger around the
   OpenClaw-compatible gateway architecture;
2. add a shared OpenClaw payload contract and metadata keys under the social
   adapter layer;
3. extend registry/profile metadata for direct versus OpenClaw-hosted adapters;
4. add a bounded generic OpenClaw gateway command and deterministic fixtures;
5. add `qq_openclaw` and OpenClaw-hosted `wechat_ilink` readiness surfaces;
6. extend closure-summary integration only after OpenClaw evidence payloads
   stabilize;
7. refresh runbooks, README docs map, and progress records;
8. run focused social regressions, then full AI Core regression, then promotion
   bundle generation.

## 7. Focused Validation

Focused regression commands:

```bash
cd /home/emb/project/zephyrproject/applocation/NeuroLink
/home/emb/project/zephyrproject/.venv/bin/python -m pytest \
  neurolink_core/tests/test_social_adapters.py \
  neurolink_core/tests/test_neurolink_core.py -q
```

Default pre-promotion handoff command:

```bash
cd /home/emb/project/zephyrproject
bash applocation/NeuroLink/scripts/run_release_2_2_3_pre_promotion_validation.sh
```

This packaged command is the preferred operator rerun because it fixes the
release-2.2.3 scope to the landed social adapter and closure-summary slices
without requiring manual `pytest -k` reconstruction.

Deterministic operator checks:

```bash
python -m neurolink_core.cli social-adapter-list
python -m neurolink_core.cli social-adapter-config --adapter wecom --enable \
  --credential-env-var WECOM_BOT_TOKEN --endpoint-url https://<wecom-endpoint>
python -m neurolink_core.cli social-adapter-test --adapter wecom
python -m neurolink_core.cli social-adapter-test --adapter wechat_ilink
python -m neurolink_core.cli social-adapter-test --adapter qq_openclaw
python -m neurolink_core.cli social-adapter-smoke
```

Bounded gateway and closure checks:

```bash
python -m neurolink_core.cli wecom-gateway-client --gateway-url wss://<wecom> \
  --access-token-env-var WECOM_BOT_TOKEN --duration 15 --max-events 1
python -m neurolink_core.cli wecom-gateway-closure \
  --gateway-run-file <wecom-gateway-run.json>
python -m neurolink_core.cli openclaw-gateway-client --gateway-url ws://<host> \
  --adapter wechat_ilink --plugin-package <plugin> --duration 15 --max-events 1
python -m neurolink_core.cli openclaw-gateway-client --gateway-url ws://<host> \
   --adapter qq_openclaw --plugin-package <operator-supplied-plugin> \
   --duration 15 --max-events 1
python -m neurolink_core.cli openclaw-gateway-closure \
   --gateway-run-file <openclaw-gateway-run.json>
python -m neurolink_core.cli closure-summary --db <core.db> \
   --session-id <session-id> \
   --wecom-gateway-file <wecom-gateway-closure.json> \
   --openclaw-gateway-file <openclaw-gateway-closure.json>
```

## 8. Promotion Boundary

Release-2.2.3 promotion may proceed only when:

1. WeCom direct deterministic and bounded gateway evidence remain green;
2. OpenClaw-hosted adapters fail closed when compliance or host/plugin evidence
   is incomplete;
3. any new OpenClaw gateway evidence is additive and does not weaken the
   promoted `qq_official` or WeCom closure gates;
4. full AI Core regression remains green before release identity changes.