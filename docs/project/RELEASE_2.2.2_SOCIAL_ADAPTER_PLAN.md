# Release 2.2.2 Social Adapter Plan

Release 2.2.2 turns the release-2.1.0 mock social foundation into the first
configurable QQ-focused social adapter slice. The goal is not to ship a full
always-on live social resident yet. The goal is to close the HLD and AI Core
LLD contract for:

1. a social adapter registry and persisted config surface;
2. official QQ Bot payload normalization;
3. OneBot/NapCat-compatible payload normalization;
4. deterministic readiness, compliance, and smoke evidence;
5. operator-facing list/config/test commands;
6. bounded official QQ webhook ingress for live callback verification;
7. bounded official QQ websocket/gateway ingress for live dispatch verification.

This release keeps live network execution optional and explicit. Deterministic
normalization, Affective-only egress, and fail-closed readiness remain the
baseline.

The deterministic contract now covers multiple bounded sample scenarios rather
than only one group-chat happy path. Release evidence can distinguish:

1. group normalization with mention-aware session routing;
2. direct-message normalization;
3. group normalization without a bot mention;
4. transport reachability evidence when an operator explicitly opts in.

## 1. Scope

Release 2.2.2 owns:

1. `qq_official` official QQ Bot adapter contract.
2. `onebot_qq` OneBot v11 / NapCat-compatible adapter contract.
3. social adapter profile registry and JSON-backed config.
4. CLI commands:
   - `social-adapter-list`
   - `social-adapter-config`
   - `social-adapter-test`
   - `qq-official-webhook-server`
   - `qq-official-gateway-client`
5. extended `social-adapter-smoke` evidence covering registry and protocol
   normalization.

Release 2.2.2 does not require by default:

1. long-running WebSocket daemons;
2. unbounded live message receive loops;
3. live outbound social sends;
4. personal-account automation acceptance for production;
5. bypassing existing Core policy, approval, or Affective-only response rules.

## 2. HLD / LLD Traceability

HLD alignment:

1. `Social Adapter` remains the normalization layer from QQ, CLI chat, and
   external channels into Core ingress envelopes.
2. user-visible output remains Affective-owned.
3. Rational Agent does not become a direct social endpoint.

AI Core LLD 5.13 alignment:

1. social adapters bind identity and permission classes;
2. normalize inbound social payloads into the same Core event path used by
   `agent-run` and replay;
3. deliver outbound Affective responses with audit records;
4. expose health and compliance metadata in smoke evidence;
5. never call Rational Agent or Unit tools directly;
6. never expose raw Rational plans, secrets, stack traces, or internal-only
   audit payloads.

## 3. Adapter Profiles

Each social adapter profile records:

1. adapter name and kind;
2. enabled flag;
3. endpoint or webhook reference;
4. credential env-var references only;
5. supported channel kinds;
6. default channel policy;
7. mention policy;
8. transport kind;
9. group session-sharing policy;
10. compliance class;
11. compliance acknowledgement state;
12. live-network allowance;
13. readiness and missing-requirement metadata.

Secret values are never persisted in config and are masked in evidence.

## 4. Compliance Stance

### 4.1 Official QQ Bot

`qq_official` is the preferred production path for QQ integration when operator
credentials are available.

Release-2.2.2 real-scene validation should start with `qq_official` by default,
and should cover all three bounded validation scenarios: `group`, `direct`,
and `group_no_mention`. When an operator explicitly approves bounded transport
probing, the same profile may enable `live_network_allowed` for a reachability
check without promoting the release into a long-running social resident.

If official QQ platform capability blocks group attachment for the current bot
type, release-2.2.2 should fall back to a direct-only live target while
retaining deterministic `group` and `group_no_mention` contract checks. That
platform limitation must be recorded as external scope pressure rather than a
Core defect.

### 4.2 OneBot / NapCat Compatibility

`onebot_qq` is treated as a lab/community bridge. It requires explicit
compliance acknowledgement before it can report live readiness. This keeps the
release aligned with the 2.2.0 contract freeze and the AI Core LLD hard
boundary on non-official bridges.

## 5. Command Surfaces

### 5.1 `social-adapter-list`

Reports configured adapter profiles, readiness, compliance metadata, missing
requirements, and masked credential references.

### 5.2 `social-adapter-config`

Allows operators to update adapter metadata without editing source code:
endpoint, webhook, credential env-var references, supported channel kinds,
mention policy, transport kind, group session-sharing policy, compliance
metadata, and enable/disable state.

### 5.3 `social-adapter-test`

Runs deterministic adapter validation. It normalizes sample inbound payloads,
verifies identity binding and Affective-only egress planning, and reports
readiness without executing live network calls by default.

An explicit `--probe-transport` mode may perform a bounded reachability probe
against the configured transport endpoint, but only when the adapter profile is
already marked with live-network allowance and compliance readiness.

An explicit `--sample-scenario` mode selects which deterministic inbound sample
contract is exercised: `group`, `direct`, or `group_no_mention`.

### 5.4 `social-adapter-smoke`

Aggregates:

1. existing Core social ingress and Affective egress proof;
2. social adapter registry readiness;
3. official QQ normalization proof;
4. OneBot normalization proof;
5. session-scope and mention-policy metadata proof;
6. social compliance metadata proof.

### 5.5 `qq-official-webhook-server`

Runs a bounded local HTTP callback server for the official QQ webhook path. It
supports callback verification (`op=13`), accepts supported official dispatch
events, normalizes them through `qq_official`, and forwards the resulting
social envelope into the normal Core event path.

This command is intentionally bounded:

1. it serves only one configured path;
2. it stops after a bounded runtime or bounded event count;
3. it does not imply a long-running production daemon;
4. it remains subject to the same Core/Affective-only response boundary.

### 5.6 `qq-official-gateway-client`

Runs a bounded official QQ websocket client. It fetches an access token from
`AppID`/`AppSecret`, fetches a gateway WSS URL, completes `HELLO`/`IDENTIFY`,
sends heartbeats, accepts supported dispatch events, normalizes them through
`qq_official`, and forwards the resulting social envelope into the normal Core
event path.

When a bounded gateway run is intended to support release closure rather than
only operator inspection, its raw output should be converted through
`qq-official-gateway-closure` and then archived as a dedicated closure payload
for `closure-summary` consumption.

This command is intentionally bounded:

1. it stops after a bounded runtime or bounded dispatch-event count;
2. it does not claim long-running resident behavior yet;
3. it can persist `session_id` / `sequence` to a local state file and make bounded `RESUME` attempts after disconnects;
4. it remains subject to the same Core/Affective-only response boundary.

## 6. Deterministic Validation

Focused validation commands:

```bash
cd /home/emb/project/zephyrproject/applocation/NeuroLink
/home/emb/project/zephyrproject/.venv/bin/python -m pytest \
  neurolink_core/tests/test_social_adapters.py \
  neurolink_core/tests/test_neurolink_core.py -q
```

Deterministic operator checks:

```bash
python -m neurolink_core.cli social-adapter-list
python -m neurolink_core.cli social-adapter-config --adapter qq_official --enable \
  --credential-env-var QQ_BOT_TOKEN --credential-env-var QQ_BOT_SECRET \
  --endpoint-url https://api.sgroup.qq.com
python -m neurolink_core.cli social-adapter-test --adapter qq_official
python -m neurolink_core.cli social-adapter-test --adapter qq_official \
   --sample-scenario direct
python -m neurolink_core.cli social-adapter-test --adapter onebot_qq \
   --sample-scenario group_no_mention
python -m neurolink_core.cli social-adapter-test --adapter onebot_qq \
   --probe-transport --probe-timeout-seconds 0.5
python -m neurolink_core.cli qq-official-webhook-server \
  --host 127.0.0.1 --port 8091 --path /qq/callback --duration 30 --max-events 1
python -m neurolink_core.cli qq-official-gateway-client \
   --duration 30 --max-events 1 \
   --session-state-file /tmp/qq-official-gateway-session.json \
   --max-resume-attempts 2
python -m neurolink_core.cli social-adapter-smoke
```

## 7. Current Boundary And Next Slice

The current release-2.2.2 boundary now includes all of the following without
promoting the feature set into a full live social resident:

1. explicit sample payload fixtures for official QQ and OneBot deployments;
2. richer mention/private/group policy metadata;
3. opt-in transport probe hooks behind explicit live-network and compliance
   gates.

The next release-2.2.2 slice should therefore focus on one or more of the
following:

1. additional direct-message and mention-edge fixture coverage;
2. optional closure-summary integration if release-2.2.2 is promoted as a
   standalone evidence milestone;
3. deployment-facing evidence summaries that separate deterministic readiness
   from transport reachability results;
4. operator-facing evidence packaging and archive layout around bounded gateway reconnect/resume runs.

The first and third items are now partially implemented through scenario-aware
sample fixtures, layered `social-adapter-test` evidence summaries, the bounded
`qq-official-webhook-server` ingress path, and the bounded
`qq-official-gateway-client` ingress path with bounded reconnect/resume support.
The closure-summary integration path is now present through a dedicated
`qq-official-gateway-closure` artifact. Remaining work is to extend that
same pattern into broader closure and deployment-facing reports if
release-2.2.2 needs a more formal promotion packet.

The current implementation already borrows two safe structural ideas from the
local QwenPaw reference tree without copying its runtime directly:

1. OneBot reverse-WebSocket transport is represented explicitly as transport
   metadata rather than hidden inside a generic endpoint string.
2. group session sharing is represented as a bounded policy flag so group-chat
   routing can choose between per-user and shared-group session scope.
