# NeuroLink Release 1.1.5 Pre-Research Baseline

## 1. Scope

Release 1.1.5 opens a larger architecture and Agent-interface track on top of
the closed release-1.1.4 baseline. The release has two primary goals:

1. Introduce a Neuro Unit protocol-v2 contract layer so Zenoh-facing payloads,
   routes, field names, statuses, error classes, and event shapes are defined
   through typed protocol structures instead of scattered string literals and
   ad hoc JSON construction.
2. Evolve `neuro_cli` from a board-test helper into an Agent-facing skill entry
   point that can initialize or diagnose the Zephyr workspace, guide app
   development workflows, control Neuro Unit boards, register MCU callbacks,
   and execute controlled local handlers when MCU events arrive.

Release-1.1.5 may intentionally break the previous Unit/CLI wire protocol when
that produces a clearer v2 contract. Human and Agent-facing CLI stdout must
remain structured JSON even if the board wire encoding later moves from JSON to
CBOR or another binary format.

Out of scope for the kickoff slice:

1. Promoting `RELEASE_TARGET` from `1.1.4` to `1.1.5` before closure evidence.
2. Replacing all payload encoders in one step.
3. Enabling unrestricted inline code execution from MCU events.
4. Reworking update state-machine semantics, lease semantics, or app runtime
   lifecycle ordering unless a protocol-v2 contract test exposes a defect.
5. Removing existing operator scripts; 1.1.5 should wrap and structure them for
   Agent use before deciding whether any script surface is redundant.

## 2. Current Baseline

Release-1.1.4 is closed in the current workspace with local, build, script,
preflight, and real-board smoke evidence. The canonical Neuro CLI release marker
currently remains:

1. `applocation/NeuroLink/neuro_cli/src/neuro_cli.py`
2. `RELEASE_TARGET = "1.1.4"`

The useful 1.1.4 foundation for this release is:

1. `neuro_unit_update_service` owns live update orchestration.
2. `neuro_unit_app_command` owns app command service policy and reply mapping.
3. `neuro_app_callback_bridge` is a runtime callback adapter.
4. `neuro_unit_dispatch` is documented as a transport-route adapter.
5. `neuro_unit_response` has started moving toward explicit DTO input through
   query-app snapshots.
6. `neuro_cli` is now the canonical top-level host-control CLI project.

The remaining protocol problem is that JSON fields, status strings, numeric
status codes, route templates, topic templates, event payloads, app command
reply shapes, and request metadata keys are still distributed across response,
event, dispatch, request, app, CLI, and script code.

## 3. Module Classification

### Stable Domain and State Modules

These modules should remain state or policy owners and should not absorb wire
encoding details:

1. `applocation/NeuroLink/neuro_unit/src/neuro_update_manager.c`
2. `applocation/NeuroLink/neuro_unit/src/neuro_lease_manager.c`
3. `applocation/NeuroLink/neuro_unit/src/neuro_artifact_store.c`
4. `applocation/NeuroLink/neuro_unit/src/neuro_app_command_registry.c`
5. `applocation/NeuroLink/neuro_unit/src/neuro_state_registry.c`

### Protocol and Presentation Candidates

These modules are the first protocol-v2 targets:

1. `applocation/NeuroLink/neuro_unit/src/neuro_unit_response.c`
   - currently builds JSON response payloads directly
   - should format from protocol DTOs or delegate to a codec module
2. `applocation/NeuroLink/neuro_unit/src/neuro_unit_event.c`
   - currently owns event route construction and app callback JSON helpers
   - should keep publish orchestration but stop owning field spelling
3. `applocation/NeuroLink/neuro_unit/src/neuro_request_envelope.c`
   - currently provides request metadata parsing and small JSON extractors
   - should become a typed protocol decoder or a compatibility wrapper
4. `applocation/NeuroLink/subprojects/neuro_unit_app/src/main.c`
   - currently parses callback config through JSON helper calls
   - should consume app-facing protocol-v2 helper APIs

### Transport and Route Edge

These modules may know about Zenoh mechanics but should share route definitions
with the protocol contract:

1. `applocation/NeuroLink/neuro_unit/src/neuro_unit_dispatch.c`
2. `applocation/NeuroLink/neuro_unit/src/zenoh/neuro_unit_zenoh.c`
3. `applocation/NeuroLink/neuro_cli/src/neuro_cli.py`

### Agent-Facing Host Control

`neuro_cli` should become a small Agent-facing control system rather than a
single testing script. The target internal split is:

1. protocol constants, route builders, payload builders, and reply decoders
2. Zenoh session/query/subscription transport helpers
3. skill/workspace initialization and script-wrapper commands
4. board-control command handlers
5. reactive event handler execution with safety defaults

## 4. Protocol-v2 Direction

The protocol layer should use typed enums and DTOs where values represent state,
status, or error classes. Raw string macros are acceptable for literal JSON/CBOR
field names and route segments, but application services should not pass around
unstructured status strings when an enum can express the contract.

Initial protocol contract contents:

1. protocol version and wire encoding identifiers
2. common request metadata fields
3. common response status and error classes
4. route and event topic templates
5. lease, query, update, app command, callback config, callback event, and state
   event DTOs
6. runtime, artifact, update, network, and dispatch state mapping helpers
7. bounded encode/decode APIs with explicit `-EINVAL`, `-ENAMETOOLONG`, and
   `-EBADMSG` style failures

### Wire Encoding Policy

Release-1.1.5 is allowed to replace the existing JSON wire payloads. The
recommended sequence is still:

1. land protocol-v2 DTO and codec boundaries first
2. keep a JSON-v2 backend initially for readability and script continuity
3. add CBOR-v2 only after Unit and CLI golden-vector tests prove binary payload
   decoding, evidence handling, and script behavior are aligned

If CBOR is selected during 1.1.5, the release must enable the Zephyr zcbor path,
add an explicit Python CBOR dependency to `neuro_cli/requirements.txt`, and
update CLI/script payload readers so they do not assume UTF-8 JSON Zenoh payloads.

## 5. Agent Skill Direction

The Agent-facing CLI surface should remain command-line driven and machine
readable. The selected delivery shape for 1.1.5 is capabilities JSON plus
documentation/prompt guidance, not a VS Code-specific customization file.

Required skill abilities:

1. initialize or diagnose the Zephyr development environment
2. guide Agent app development against the Neuro Unit app framework
3. build app artifacts, build/flash Unit firmware, and run preflight/smoke paths
4. send board commands and deploy/update actions through Neuro Unit
5. register MCU app callbacks and subscribe to MCU-originated events
6. execute controlled local command or Python handler files when matching MCU
   events arrive

Callback handler execution must be subprocess based by default:

1. pass event JSON through stdin
2. capture stdout, stderr, exit code, duration, and timeout state
3. require a bounded handler timeout
4. avoid shell interpretation unless explicitly requested
5. constrain handler working directory to the workspace or configured sandbox
6. cap event payload size and max event count
7. emit audit JSON in CLI output

Inline arbitrary code strings are intentionally excluded from the default 1.1.5
contract because they are harder to audit and easier to misuse.

## 6. Workstreams

### WS-1 Protocol Surface Inventory and Guardrails

1. Lock current response, event, request, and route shapes in focused tests.
2. Make intentional wire-shape changes visible through explicit expected-output
   updates.
3. Add representative CLI tests for Unit reply parsing and payload construction.

### WS-2 Protocol-v2 Contract and Codec

1. Add `neuro_protocol.h` or equivalent naming aligned with local style.
2. Add typed status/error enums and mapping functions.
3. Add protocol DTOs and bounded encode/decode helpers.
4. Migrate response, event, request, and app callback code to the codec.
5. Decide JSON-v2 versus CBOR-v2 as a contained sub-slice with tests.

### WS-3 Route and Topic Normalization

1. Centralize Unit route and event topic builders.
2. Replace hardcoded route strings in dispatch and Zenoh queryable declaration.
3. Mirror route builders in Neuro CLI through a Python protocol module.
4. Add route construction tests across query, lease, app, update, and event
   surfaces.

### WS-4 Neuro CLI Protocol and Transport Split

1. Split Python protocol constants, builders, and decoders out of the monolithic
   CLI entrypoint.
2. Normalize error categories for no-reply, decode failure, Zenoh error reply,
   board-side error status, unsupported protocol version, and handler failure.
3. Preserve Agent-facing stdout JSON envelopes.

### WS-5 Agent Skill Initialization and Workflows

1. Add skill or workspace initialization diagnostics that reuse
   `setup_neurolink_env.sh` behavior without pretending a child process can
   mutate the parent shell.
2. Add structured wrappers for app build, Unit build/flash, preflight, smoke,
   board preparation, and UART capture guidance.
3. Expand `capabilities` output with protocol version, wire encoding,
   release target, command schema, lease requirements, board requirements, and
   reactive callback support.

### WS-6 Reactive Callback Handler Execution

1. Add monitor options for local command and Python handler execution.
2. Implement timeout, max-events, payload-size, cwd, and audit-output guardrails.
3. Test success, timeout, nonzero exit, invalid handler output, and cleanup.
4. Validate a real callback path with harmless handler execution when hardware is
   available.

## 7. Acceptance Criteria

1. Protocol fields, statuses, error classes, and routes are defined in one
   protocol contract layer and consumed by Unit and CLI code.
2. Response/event/request builders consume typed DTOs or protocol decode results
   rather than assembling or parsing scattered ad hoc JSON.
3. Any chosen wire-shape or wire-encoding break is documented, tested, and
   represented in capabilities output.
4. `neuro_cli` exposes Agent-readable capabilities and initialization
   diagnostics.
5. Agent app-development and board-control workflows are available through
   structured CLI commands or documented command plans.
6. MCU event callbacks can trigger controlled local command or Python handler
   execution with audit output and safety defaults.
7. CLI stdout remains structured JSON for Agent consumption.
8. Release identity is promoted to `1.1.5` only after local, build, script,
   preflight, smoke, and callback-handler evidence is recorded.

## 8. Verification Gates

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`
2. `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q`
4. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py`
5. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
6. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
7. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check`
8. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check`
9. `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text`
10. `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5`

Additional 1.1.5-specific gates:

1. Unit protocol encode/decode golden vectors for all core DTOs.
2. Unit route/topic builder tests for query, lease, app, update, and event paths.
3. CLI protocol builder/decoder tests matching Unit golden vectors.
4. Skill initialization JSON output test.
5. Reactive callback handler tests for command and Python handlers.
6. If CBOR is enabled, C and Python CBOR golden-vector round trips plus script
   evidence parsing updates.

## 9. Initial Execution Slices

1. `EXEC-139`: release-1.1.5 kickoff baseline and ledger entry.
2. `EXEC-140`: protocol surface inventory and current-shape guardrail tests.
3. `EXEC-141`: introduce `neuro_protocol` definitions for common fields,
   statuses, errors, and route/topic builders.
4. `EXEC-142`: add protocol DTO and JSON-v2 codec entry points.
5. `EXEC-143`: migrate Unit response builders to protocol DTO/codec.
6. `EXEC-144`: migrate event key/payload and app command reply helpers to
   protocol DTO/codec.
7. `EXEC-145`: migrate request metadata and callback config parsing to protocol
   decode helpers.
8. `EXEC-146`: split Neuro CLI protocol builders/decoders into a Python module.
9. `EXEC-147`: add Agent skill initialization and expanded capabilities output.
10. `EXEC-148`: add structured app-development and board-operation workflows.
11. `EXEC-149`: add controlled reactive callback handler execution.
12. `EXEC-150`: decide whether CBOR-v2 lands in 1.1.5 or remains behind a
    documented protocol backend extension point.
13. `EXEC-151`: release-1.1.5 closure gates.
14. `EXEC-152`: release identity promotion to `1.1.5` after evidence.

## 10. Risks

### EXEC-140 Protocol Guardrail Status (2026-04-26)

`EXEC-140` added current-shape protocol guardrails before protocol-v2
replacement. The slice intentionally preserves existing JSON strings and route
shapes while making later drift visible in tests.

Coverage added:

1. callback app event key and payload contract
2. app command reply JSON contract
3. dispatch lease release route handling
4. dispatch query device/apps/leases route handling
5. unsupported command/query/update status-code mapping
6. Neuro CLI lease acquire payload contract
7. Neuro CLI app invoke `--args-json` payload contract
8. Neuro CLI prepare/artifact provider payload contract
9. Neuro CLI reply parsing and payload-level `status=error` contract

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`31` tests)
2. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS

### EXEC-141 Protocol Contract Status (2026-04-26)

`EXEC-141` introduced the initial protocol-v2 contract header without migrating
runtime call sites yet. The new `neuro_protocol.h` establishes:

1. protocol version `2.0`
2. wire encoding identifiers for `json-v2` and `cbor-v2`
3. common request/reply field-name constants
4. typed status and error-code enums
5. query, lease, update, command, and event route builders
6. token validation and explicit route buffer error behavior

Verification:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
2. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`31` tests)

### EXEC-142 Protocol JSON-v2 Codec Entry Status (2026-04-26)

`EXEC-142` added the first protocol DTO and JSON-v2 codec entry points without
migrating existing response/event builders yet. The codec currently covers the
highest-churn payload families that will be migrated first:

1. error replies
2. lease acquire/release replies
3. query-device replies
4. app callback event payloads
5. app command reply payloads

The slice keeps JSON-v2 human-readable while making wire encoding an explicit
backend decision point for later CBOR work.

Verification:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
2. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)

### EXEC-143 Response Builder Codec Migration Status (2026-04-26)

`EXEC-143` migrated the lowest-risk response builders to the new protocol codec
while preserving the current JSON output contracts. The migrated builders are:

1. `neuro_unit_build_error_response`
2. `neuro_unit_build_lease_acquire_response`
3. `neuro_unit_build_lease_release_response`
4. `neuro_unit_build_query_device_response`

`query-apps` and `query-leases` remain on their legacy builders until a broader
DTO surface exists for those payloads.

Verification:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
2. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
3. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS

### EXEC-144 Event and App Reply Codec Migration Status (2026-04-26)

`EXEC-144` migrated event key construction and app-facing event/reply payloads
onto `neuro_protocol` route builders and `neuro_protocol_codec` DTO encoders.
`neuro_unit_event` remains the configuration and publish orchestration module;
the protocol layer now owns field spelling and route formatting for the migrated
surfaces.

Verification:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
2. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
3. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS before formatting; source formatting changed no behavior

### EXEC-145 Request and Callback Config Decode Migration Status (2026-04-26)

`EXEC-145` migrated request metadata parsing and sample app callback
configuration parsing onto protocol JSON-v2 decode helpers. The protocol codec
now owns DTO decode surfaces for:

1. request metadata fields: `request_id`, `source_core`, `source_agent`,
   `target_node`, `lease_id`, `idempotency_key`, `timeout_ms`, `priority`, and
   `forwarded`
2. app callback config fields: `callback_enabled`, `trigger_every`, and
   `event_name`

`neuro_request_metadata_parse()` now delegates field spelling and default decode
behavior to `neuro_protocol_decode_request_metadata_json()`. The sample app now
uses the public `neuro_unit_read_callback_config_json()` helper with explicit
field-presence flags instead of direct JSON extractor calls, while the legacy
`neuro_json_extract_string/int/bool()` helpers remain available for existing
Unit and LLEXT compatibility paths.

Verification:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
2. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
3. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS

### EXEC-146 Neuro CLI Protocol Module Split Status (2026-04-26)

`EXEC-146` split the Python-side protocol helpers out of the monolithic
`neuro_cli.py` entrypoint. The new `neuro_protocol.py` module owns:

1. protocol version and wire encoding markers
2. the capability matrix data source
3. route builders for query, lease, app command, update, event subscription, app
   event subscription, and artifact paths
4. base/write/protected/app-callback payload builders
5. payload validation policy
6. reply JSON decoding

`neuro_cli.py` now calls the protocol module for route construction and protocol
helper behavior while preserving the historical helper function names as a
compatibility façade for tests and scripts.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`34` tests)

### EXEC-147 Agent Init and Capabilities Expansion Status (2026-04-26)

`EXEC-147` added Agent-facing initialization diagnostics and expanded capability
metadata. `system init --output json` now reports workspace readiness, protocol
version, wire encoding, script discovery, shell setup guidance, Agent workflow
commands, and verification command plans without opening a Zenoh session.
`system capabilities --output json` now reports protocol and Agent skill metadata
alongside the existing capability matrix.

The CLI explicitly reports that child-process diagnostics cannot mutate the
parent shell and provides the recommended `source` command for environment
setup instead.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`37` tests)
3. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --output json system init` => PASS (`ok: true`, `status: ready`)
4. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --output json system capabilities` => PASS (`ok: true`, protocol metadata present)

### EXEC-148 Structured Workflow Plan Commands Status (2026-04-26)

`EXEC-148` added Agent-readable workflow plan commands for app-development,
verification, and board-operation paths. The new `workflow plan <name>` and
`system workflow plan <name>` commands emit structured JSON containing command
plans, expected artifacts, workflow category, protocol metadata, and an explicit
`executes_commands: false` marker.

Supported workflow plans:

1. `app-build`
2. `unit-build`
3. `unit-edk`
4. `unit-tests`
5. `cli-tests`
6. `preflight`
7. `smoke`

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`39` tests)
3. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --output json workflow plan app-build` => PASS (`ok: true`)
4. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --output json system workflow plan preflight` => PASS (`ok: true`)

### EXEC-149 Controlled Reactive Callback Handler Execution Status (2026-04-26)

`EXEC-149` added opt-in subprocess handler execution for event monitoring.
Handler execution is disabled by default and can be enabled on `events`,
`app-events`, `monitor events`, and `monitor app-events` with either:

1. `--handler-command`, parsed without a shell and executed with
   `subprocess.run(shell=False)`
2. `--handler-python`, executed through the active Python interpreter

Event JSON is passed through stdin. Handler audit output records stdout, stderr,
return code, duration, timeout state, and error status. Guardrails include
handler timeout, handler cwd constrained to the workspace root, max event JSON
bytes, and max event count.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`42` tests)

### EXEC-150 Wire Backend Decision Status (2026-04-26)

`EXEC-150` keeps JSON-v2 as the only enabled release-1.1.5 wire encoding and
keeps CBOR-v2 as a documented extension point. The decision is exposed through
CLI protocol metadata:

1. `wire_encoding: json-v2`
2. `supported_wire_encodings: ["json-v2"]`
3. `planned_wire_encodings: ["cbor-v2"]`
4. `cbor_v2_enabled: false`

CBOR-v2 should land only after Unit zcbor enablement, Python dependency
selection, Unit/Python golden-vector round trips, script parser updates, and
evidence tooling are implemented together.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`42` tests)
3. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --output json system capabilities` => PASS (`wire_encoding: json-v2`, `cbor_v2_enabled: false`)

### EXEC-151 Local Closure Gate Status (2026-04-26)

`EXEC-151` completed all local closure gates available in this workspace. The
first hardware attempt was initially blocked because no `/dev/ttyACM*` or
`/dev/ttyUSB*` device was visible in the Linux environment; that blocker was
resolved during `EXEC-152` by mapping the Windows USB device into WSL.

Local verification:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`26` tests)
2. `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh` => PASS
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`42` tests)
4. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
5. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
6. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`7` script tests)
7. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS
8. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS

Initial hardware gate status:

1. `ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true` => no serial devices found
2. serial-required preflight and real-board smoke were deferred until USB pass-through was available

### EXEC-152 Hardware Closure and Release Identity Promotion Status (2026-04-26)

`EXEC-152` completed the release-1.1.5 hardware closure and promoted the
canonical Neuro CLI release identity to `1.1.5`.

USB pass-through and board preparation:

1. `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --attach-only` => PASS (`BUSID 8-4`, `/dev/ttyACM0`)
2. initial serial-required preflight after attach => FAIL with `no_reply_board_unreachable` while router and serial were present
3. `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --device /dev/ttyACM0 --node unit-01 --capture-duration-sec 60` => PASS (`NETWORK_READY`, IPv4 `192.168.2.69`)

Hardware smoke evidence:

1. `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5` => PASS
2. evidence: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260426-034446.ndjson`

Release identity promotion:

1. `RELEASE_TARGET` in `applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => `1.1.5`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`42` tests)
4. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --output json system capabilities` => PASS (`release_target: 1.1.5`)

Release-1.1.5 is closed against the current local and hardware evidence.

## 11. Risks

1. Switching wire encoding can break smoke/preflight scripts that parse CLI JSON
   replies or assume Unit Zenoh payloads are text.
2. CBOR adds useful structure and compactness but reduces live debugging
   visibility unless CLI decode tooling and evidence records are excellent.
3. App-facing helper ABI changes can break existing LLEXT artifacts; release
   1.1.5 allows this, but the EDK/app build gates must prove the new contract.
4. Agent callback handler execution can become unsafe if shell execution,
   working directory, timeouts, or event payload size are not constrained.
5. A protocol abstraction that only wraps strings without typed states/errors
   would not solve the maintenance problem.

## 12. Rollback Strategy

1. Keep protocol inventory tests before protocol replacement so changes can be
   classified as intentional or accidental.
2. Land route constants/builders before moving payload encoders.
3. Keep JSON-v2 backend available until any CBOR-v2 path has equivalent Unit,
   CLI, script, and hardware evidence.
4. Treat Agent handler execution as opt-in; rollback can remove handler options
   while preserving passive event monitoring.
5. `RELEASE_TARGET` was kept at `1.1.4` until `EXEC-152`; after hardware closure
   evidence passed it was promoted to `1.1.5`.

## 13. Release Identity Policy

`applocation/NeuroLink/neuro_cli/src/neuro_cli.py` remained at
`RELEASE_TARGET = "1.1.4"` throughout implementation. `EXEC-152` promoted the
identity to `1.1.5` only after local gates, USB pass-through, serial-required
preflight recovery, and Linux smoke evidence passed.