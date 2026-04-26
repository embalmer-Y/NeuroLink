# NeuroLink Release 1.1.6 Pre-Research Baseline

## 1. Scope

Release 1.1.6 opens a framework-level protocol, Unit architecture, and Agent
skill maturity track on top of the closed release-1.1.5 baseline. This release
is intentionally not a minimal optimization pass. The target is the most
coherent long-term framework shape for NeuroLink, with bounded execution slices
and evidence gates so the larger changes remain reviewable.

Primary goals:

1. Replace the Neuro Unit runtime wire payload encoding from JSON-v2 to
   CBOR-v2. The final release-1.1.6 runtime target is CBOR-only; JSON-v2 may
   remain only for offline fixtures, debug conversion, or migration tests.
2. Deeply review and improve `neuro_unit` for extensibility and reuse. The goal
   is clearer framework boundaries, typed contracts, reusable service DTOs, and
   transport-edge isolation rather than file movement for its own sake.
3. Add API documentation comments to exposed Neuro Unit interfaces and add
   necessary structured debug information around protocol, dispatch, update,
   callback, event, and app-runtime paths.
4. Promote `neuro_cli` into a mature project-shared Agent skill that can set up
   or verify the Zephyr development environment, guide Agents through Neuro
   Unit app development, build/debug/flash/upload workflows, issue commands to
   MCU boards, register MCU callbacks, and execute flexible local Agent code in
   callback flows with explicit audit records.

Out of scope for the kickoff slice:

1. Promoting `RELEASE_TARGET` from `1.1.5` to `1.1.6` before closure evidence.
2. Enabling a hidden JSON runtime fallback after the CBOR-only cutover.
3. Changing lease semantics, update state-machine semantics, route key
   expressions, or app runtime lifecycle ordering unless a focused contract
   decision and tests justify the change.
4. Silently executing local callback code. Callback execution can become broad
   in this release, but every execution path must be explicit, auditable, and
   visible in CLI output or evidence.

## 2. Current Baseline

Release-1.1.5 is closed in the current workspace with local, build, script,
preflight, and real-board smoke evidence. The canonical Neuro CLI release marker
currently remains:

1. `applocation/NeuroLink/neuro_cli/src/neuro_cli.py`
2. `RELEASE_TARGET = "1.1.5"`

Useful release-1.1.5 foundations:

1. `neuro_protocol.h` defines protocol version `2.0`, wire encoding names,
   route builders, status enums, error classes, and field constants.
2. `neuro_protocol_codec` owns the first DTO encode/decode layer, currently
   backed by JSON-v2.
3. Response, event, request metadata, callback config, and Python CLI protocol
   helpers have started moving away from scattered string construction.
4. `neuro_cli` now exposes Agent-facing `system init`, `system capabilities`,
   and workflow plan commands.
5. Event monitoring supports opt-in subprocess handler execution with timeout,
   bounded payload size, workspace cwd constraints, and audit output.
6. CBOR-v2 is already named as a planned protocol concept, but it is not enabled
   in Unit runtime, Python CLI, scripts, evidence tooling, or capabilities.

The workspace already includes the Zephyr zcbor module, but current NeuroLink
build outputs show the module present while `CONFIG_ZCBOR` is not enabled. The
release-1.1.6 CBOR work must therefore include explicit Kconfig/build enablement
instead of assuming module availability is enough.

## 3. Release Decisions

### Wire Encoding Decision

The final release-1.1.6 runtime wire encoding is CBOR-v2 only:

1. Unit request decode, reply encode, app event encode, and callback config
   decode use CBOR-v2.
2. Neuro CLI sends and receives binary CBOR payloads at the Zenoh boundary.
3. CLI stdout and script evidence remain structured JSON/NDJSON for humans,
   Agents, and CI tooling.
4. Capabilities output reports `wire_encoding: cbor-v2`,
   `supported_wire_encodings: ["cbor-v2"]`, and `cbor_v2_enabled: true` after
   the cutover slice.
5. JSON-v2 runtime support is not advertised as a release-1.1.6 fallback.

### Agent Skill Decision

The Neuro CLI skill is project-shared. The current
`applocation/NeuroLink/neuro_cli/skill/SKILL.md` is treated as a seed. The
release should either mirror or promote it into a standard project discovery
path such as `.github/skills/neuro-cli/SKILL.md`, with scripts and references
kept close enough for progressive loading.

### Callback Execution Decision

Callback execution should be flexible enough for Agent workflows, including
multiple local runner forms where useful. Because MCU-originated events can
trigger local code, every runner must require explicit opt-in and must emit
audit details: runner type, argv or script identity, cwd, timeout, duration,
return code, stdout/stderr capture, payload size, and error classification.

## 4. Architecture Direction

### Protocol and Codec Boundary

The protocol layer should be schema-led and DTO-led. Application services should
construct and consume typed structs. Only the protocol codec backend should know
whether those structs are encoded as CBOR bytes, JSON fixture text, or debug
pretty-print output.

Target boundaries:

1. `neuro_protocol.h`: protocol version, wire encoding identifiers, field/key
   IDs, status/error enums, route builders, token validation, and stable limits.
2. `neuro_protocol_codec.h`: format-neutral DTOs and encode/decode APIs.
3. `neuro_protocol_codec_cbor.c`: zcbor-backed runtime CBOR-v2 encode/decode.
4. Optional fixture/debug helpers: JSON conversion may exist for tests and
   diagnostics, but not as the runtime backend.
5. Python `neuro_protocol.py`: route builders, logical DTO builders, CBOR
   encode/decode, golden-vector helpers, and CLI reply classification.

### Neuro Unit Framework Boundary

The Unit framework should converge around reusable contracts:

1. Transport adapters receive Zenoh queries and payload bytes.
2. Route parsing produces route/action DTOs instead of scattering string
   matching through service paths.
3. Request decode produces metadata and command DTOs.
4. Application services consume request DTOs and return service result DTOs.
5. Response/event modules encode result DTOs through the protocol codec.
6. Diagnostics use correlation fields from a shared request/reply context.

High-value review targets:

1. `neuro_unit_dispatch.c`: replace repeated route string assembly and direct
   comparisons with route helpers or a table-driven dispatch contract.
2. `neuro_unit_response.c`: complete typed DTO coverage for query-apps,
   query-leases, and update result families.
3. `neuro_request_envelope.c`: reduce legacy JSON extractor responsibility and
   become a compatibility wrapper or decode adapter.
4. `neuro_unit_update_service.c`: preserve state-machine behavior while making
   request/reply context and diagnostics more explicit.
5. `neuro_unit_app_command.c` and `neuro_app_callback_bridge.c`: clarify app
   command service versus app-runtime callback responsibilities.
6. `neuro_unit_event.c`: keep publish orchestration but move field/key encoding
   fully into protocol DTOs.
7. Port FS/network, shell extension, runtime app API, and EDK include packaging:
   keep these as reusable provider and app-facing extension seams.

## 5. Agent Skill Direction

The skill should teach Agents to use NeuroLink's supported control surfaces
instead of improvising command sequences. It should be progressively loaded and
workflow-oriented.

Required skill capabilities:

1. Initialize or verify the Zephyr workspace and Python environment.
2. Run or request workflow plans for Unit build, Unit tests, app build, EDK
   build, flash, board preparation, preflight, smoke, and deploy flows.
3. Guide an Agent through creating a Neuro Unit app against the public app API
   and EDK headers.
4. Send board commands and update operations through Neuro CLI in the documented
   lease/order sequence.
5. Register MCU callbacks, monitor MCU events, and invoke local callback
   handlers.
6. Collect and summarize evidence files for release gates.
7. Provide troubleshooting branches for missing Zephyr environment, missing
   Python CBOR dependency, missing serial device, no-reply board state, router
   startup failure, CBOR decode failure, and callback handler failure.

Skill packaging work:

1. Add project-shared skill frontmatter with a keyword-rich description.
2. Keep `SKILL.md` concise and move detailed command matrices or app templates
   into references/assets where useful.
3. Upgrade `invoke_neuro_cli.py` into a robust wrapper that always uses
   `--output json`, validates both process exit code and payload status, and
   surfaces CBOR dependency/setup issues clearly.
4. Add examples for app skeleton creation, callback handler runners, deploy
   sequence, and evidence collection.

## 6. Workstreams

### WS-1 Release Baseline and Guardrails

1. Record this baseline and kickoff ledger entry.
2. Add or confirm tests that lock release-1.1.5 JSON behavior before CBOR
   replacement.
3. Inventory every request, reply, and event payload family that must receive a
   CBOR fixture.
4. Keep release identity at `1.1.5` until final closure evidence.

### WS-2 CBOR Schema and Unit Codec

1. Decide map-key style for CBOR-v2. Recommended: compact integer keys with a
   documented mapping and CLI debug pretty-printer.
2. Add stable DTO and key definitions to protocol headers.
3. Enable `CONFIG_ZCBOR` through a NeuroLink Kconfig switch.
4. Implement zcbor-backed encode/decode functions for common metadata, errors,
   lease replies, query replies, app command config/reply, update payloads, and
   events.
5. Add malformed/truncated/oversized CBOR negative tests.

### WS-3 Unit Runtime Cutover

1. Migrate request metadata and callback config decode from JSON to CBOR.
2. Migrate response/event/app reply encoders from JSON to CBOR.
3. Keep Zenoh key expressions stable unless a separate route decision is made.
4. Add structured protocol diagnostics through `neuro_unit_diag`.
5. Remove runtime JSON advertisement from capabilities after the cutover.

### WS-4 Python CLI CBOR Cutover

1. Add a Python CBOR dependency to `neuro_cli/requirements.txt`.
2. Encode outgoing Unit requests as CBOR bytes.
3. Decode Unit replies and events from CBOR bytes.
4. Keep CLI stdout JSON envelopes stable for Agents and scripts.
5. Add C/Python cross-language golden-vector tests.

### WS-5 Framework Reuse and Extensibility Review

1. Refactor dispatch toward table-driven or route-helper based routing.
2. Introduce or strengthen shared request/reply context.
3. Expand DTO coverage for query-apps, query-leases, and update result payloads.
4. Clarify callback bridge and app command service ownership.
5. Review app-facing APIs and port/provider contracts for reusable extension
   patterns.

### WS-6 API Documentation and Diagnostics

1. Add Doxygen-style comments to public and EDK-facing headers.
2. Document buffer ownership, lifetimes, return codes, thread/context rules,
   max lengths, and stability expectations.
3. Add bounded debug logs for protocol failures, route dispatch, metadata
   validation, update transactions, event publication, and callback execution.
4. Update developer docs for adding commands/events/protocol DTOs.

### WS-7 Mature Project-Shared Skill

1. Promote or mirror the existing skill into a standard project-shared skill
   path.
2. Add environment setup and workflow execution guidance.
3. Add app-development and callback-handler templates.
4. Add wrapper tests and skill frontmatter validation.
5. Integrate skill guidance with `system init`, `system capabilities`, and
   workflow commands.

### WS-8 Closure and Release Identity

1. Run local, build, script, CBOR vector, skill, and hardware gates.
2. Capture fresh preflight, smoke, deploy, and callback execution evidence.
3. Promote `RELEASE_TARGET` to `1.1.6` only after closure evidence passes.

## 7. Acceptance Criteria

1. CBOR-v2 is the only enabled runtime wire encoding for Unit/CLI board traffic.
2. Unit and Python CLI share golden vectors for every core request/reply/event
   payload family.
3. CLI stdout, scripts, and evidence remain Agent-readable JSON/NDJSON even when
   wire payloads are binary CBOR.
4. `system capabilities` and `system init` report the 1.1.6 protocol state
   accurately.
5. Unit dispatch and service boundaries are more extensible than the 1.1.5
   baseline, with tests proving behavior compatibility or documenting deliberate
   contract changes.
6. Exposed Unit headers have useful API comments covering ownership, lifetime,
   limits, return codes, and extension rules.
7. Debug output provides actionable correlation and failure classification
   without dumping large binary payloads by default.
8. The project-shared Neuro CLI skill can guide Agents through setup, app
   development, build, flash, deploy, command, callback registration, callback
   handler execution, and evidence collection.
9. Callback handler execution supports flexible local runner forms selected for
   the release, with explicit opt-in and audit output for every execution.
10. Release identity is promoted to `1.1.6` only after local, build, script,
    CBOR-vector, skill, preflight, smoke, deploy, and callback evidence passes.

## 8. Verification Gates

Local gates:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q`
3. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`
4. `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
5. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
6. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
7. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check`
8. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check`

CBOR-specific gates:

1. Unit CBOR encode golden-vector tests.
2. Unit CBOR decode golden-vector tests.
3. Python CBOR encode/decode golden-vector tests.
4. Cross-language fixture equality checks.
5. Malformed, truncated, wrong-version, missing-field, oversized, and wrong-type
   decode rejection tests.
6. Script/evidence paths proving binary Unit payloads still become JSON/NDJSON
   evidence.

Skill and workflow gates:

1. Skill frontmatter and discovery path validation.
2. Neuro CLI wrapper tests for `--output json`, payload-status failure, and CBOR
   dependency diagnostics.
3. Workflow plan and setup dry-run tests.
4. Callback runner success, timeout, nonzero, oversized payload, cwd, and audit
   tests.

Hardware gates:

1. USB attach or board serial visibility check.
2. Board preparation as needed.
3. Serial-required preflight.
4. Linux smoke.
5. App deploy prepare/verify/activate smoke.
6. Callback registration and callback-handler execution smoke with evidence.

## 9. Initial Execution Slices

1. `EXEC-153`: release-1.1.6 kickoff baseline and ledger entry.
2. `EXEC-154`: protocol payload inventory and release-1.1.5 JSON guardrails.
3. `EXEC-155`: CBOR-v2 schema/key mapping and golden-vector fixture structure.
4. `EXEC-156`: Unit Kconfig/build enablement for zcbor and CBOR codec façade.
5. `EXEC-157`: Unit CBOR encode/decode implementation for common metadata,
   errors, lease, query-device, callback event, and app command reply.
6. `EXEC-158`: CBOR coverage for query-apps/query-leases/update/app callback
   config payloads.
7. `EXEC-159`: Unit runtime call-site cutover from JSON-v2 to CBOR-v2.
8. `EXEC-160`: Python CLI CBOR dependency, builders, decoders, and stdout
   compatibility.
9. `EXEC-161`: script/evidence binary-payload alignment.
10. `EXEC-162`: dispatch/request-reply context extensibility refactor.
11. `EXEC-163`: public API comments and structured diagnostics pass.
12. `EXEC-164`: project-shared Neuro CLI skill packaging and wrapper upgrade.
13. `EXEC-165`: broad callback runner expansion with audit and tests.
14. `EXEC-166`: local closure gates.
15. `EXEC-167`: hardware closure, callback/deploy smoke, and release identity
    promotion.

Slice numbering may change if guardrail tests expose a required intermediate
fix, but any split should preserve the same release boundaries.

## 10. Risks

1. CBOR-only runtime can break scripts, smoke evidence, or Agent tooling that
   accidentally depended on raw JSON Zenoh payload text.
2. CBOR improves structure and size but reduces live readability unless CLI
   decode tools, bounded debug previews, and evidence records are strong.
3. zcbor enablement may affect code size, stack usage, or heap pressure on the
   target board.
4. Integer-key CBOR maps improve efficiency but require excellent schema docs
   and debug pretty-printers to remain maintainable.
5. Broad local callback execution can become unsafe or confusing if opt-in,
   audit, timeout, cwd, and output handling are not consistently enforced.
6. Framework refactors can accidentally change update or lease semantics; these
   paths need guardrail tests before service-boundary cleanup.
7. Project-shared skill discovery can fail silently if frontmatter is wrong or
   the path is non-standard.

## 11. Rollback Strategy

1. Keep JSON-v2 behavior guardrails until CBOR golden vectors prove replacement
   parity or deliberate contract changes.
2. Land CBOR schema and fixture tests before production call-site cutover.
3. Keep release identity at `1.1.5` until all closure gates pass.
4. If CBOR runtime fails late, rollback can restore JSON-v2 call sites and
   capability metadata while preserving schema/fixture documents for a later
   release.
5. If callback runner expansion is rejected or unsafe, rollback can return to
   the 1.1.5 opt-in subprocess model while preserving passive event monitoring.
6. If skill packaging path is disputed, keep the existing `neuro_cli/skill`
   seed and document the standard path migration as a follow-up rather than
   blocking protocol closure.

## 12. Release Identity Policy

`applocation/NeuroLink/neuro_cli/src/neuro_cli.py` must remain at
`RELEASE_TARGET = "1.1.5"` throughout implementation. A final identity-promotion
slice may set it to `1.1.6` only after local gates, CBOR vector gates, skill
gates, script gates, serial-required preflight, Linux smoke, deploy smoke, and
callback handler evidence pass.

## 13. Execution Status

### EXEC-154 Protocol Payload Inventory and JSON Guardrails

`EXEC-154` inventoried the release-1.1.5 JSON-v2 runtime payload surface before
the CBOR-v2 schema work starts. The inventory is recorded in
`applocation/NeuroLink/docs/project/RELEASE_1.1.6_PROTOCOL_PAYLOAD_INVENTORY.md`
and classifies current request, reply, and event payload families by route,
field set, and guardrail status.

Guardrail coverage strengthened in this slice:

1. Unit update service success replies now have exact JSON-v2 contract checks
   for prepare, verify, activate, and rollback.
2. Neuro CLI request payload tests now explicitly lock base/write/protected
   payload construction, query request routing, lease release payloads, update
   verify payloads, and update activate payloads.
3. Existing Unit response, codec, event, dispatch, request metadata, app invoke,
   callback config, lease acquire, prepare payload, and payload-status error
   guardrails remain the reference baseline for later CBOR conversion.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`47` tests)
2. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`33` tests)
3. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
4. `git diff --check` => PASS

### EXEC-155 CBOR-v2 Schema and Fixture Structure

`EXEC-155` defined the first release-1.1.6 CBOR-v2 schema/key map and fixture
structure while intentionally leaving runtime Unit and CLI payloads on JSON-v2.
The schema is documented in
`applocation/NeuroLink/docs/project/RELEASE_1.1.6_CBOR_V2_SCHEMA.md` and mirrored
by the machine-readable fixture manifest at
`applocation/NeuroLink/neuro_cli/tests/fixtures/protocol_cbor_v2_schema.json`.

Schema coverage added in this slice:

1. `neuro_protocol.h` now has stable CBOR-v2 message-kind identifiers for
   request, reply, callback event, update event, and state event families.
2. `neuro_protocol.h` now has compact integer CBOR keys for shared metadata,
   error fields, lease fields, device state, app/update fields, query aggregate
   fields, callback fields, and framework diagnostics.
3. `neuro_protocol.py` mirrors the same message-kind and key maps for CLI-side
   builders, decoders, and future golden-vector tooling.
4. Unit protocol tests lock representative numeric constants so accidental key
   or kind renumbering is caught early.
5. CLI tests verify that the JSON fixture manifest remains synchronized with the
   Python protocol constants and that key/kind values are unique.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`48` tests)
3. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
4. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
5. `git diff --check` => PASS

### EXEC-156 zcbor Enablement and CBOR Codec Facade

`EXEC-156` added the first zcbor-backed CBOR-v2 codec façade while keeping all
runtime Unit and CLI wire payload call sites on JSON-v2. This slice proves the
build dependency, canonical CBOR mode, and common envelope encode/decode path
before broader DTO implementation starts.

Build and façade coverage added in this slice:

1. `CONFIG_NEUROLINK_PROTOCOL_CBOR` now owns NeuroLink CBOR-v2 codec support and
   selects `ZCBOR` plus `ZCBOR_CANONICAL`.
2. The Unit app and native_sim unit-test app compile `neuro_protocol_codec_cbor.c`
   when the NeuroLink CBOR switch is enabled.
3. `neuro_protocol_codec_cbor.h` exposes a small façade for common envelope
   header encode/decode and message-kind validation.
4. The canonical envelope header `{0: 2, 1: query_request}` is locked as the
   CBOR bytes `a200020101`.
5. Unit tests cover successful envelope encode/decode plus null input,
   undersized buffer, unsupported schema version, unknown message kind, and
   truncated payload rejection.

Verification:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
2. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`48` tests)
4. `git diff --check` => PASS

### EXEC-159A Binary Transport and CLI CBOR Bridge

`EXEC-159A` splits the runtime cutover into a lower-risk staging slice. It adds
binary transport support and Python CBOR bridge helpers before flipping every
Unit handler and CLI command call site to CBOR-v2.

Infrastructure added in this slice:

1. Unit Zenoh transport can extract query payload bytes, reply with binary
   payloads, and publish binary event payloads.
2. Unit response boundary can build CBOR responses for error, lease
   acquire/release, query-device, query-apps snapshot, and query-leases payloads.
3. Unit response tests validate generated CBOR payloads by decoding their common
   envelope and checking message-kind classification.
4. Python protocol helpers can encode and decode the initial CBOR-v2 schema
   subset without an extra runtime dependency.
5. Python reply parsing can recognize binary CBOR replies and expose decoded
   JSON-style logical payloads to existing CLI result handling.
6. Python fixture tests now match the initial Unit golden vectors for envelope
   and error reply payloads.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`51` tests)
3. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
4. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
5. `git diff --check` => PASS

### EXEC-160A CLI Outgoing CBOR Cutover

`EXEC-160A` switches the CLI side of runtime Unit query payload construction to
CBOR-v2 while preserving JSON stdout and JSON dry-run/result envelopes. Unit
request handlers still need the matching decode cutover before live board
traffic can pass end-to-end.

CLI behavior added in this slice:

1. Protocol metadata now reports `wire_encoding: cbor-v2`,
   `supported_wire_encodings: ["cbor-v2"]`, no planned runtime encodings, and
   `cbor_v2_enabled: true`.
2. CLI route helpers map stable Zenoh key expressions to CBOR message kinds for
   query, lease, app command/callback config, and update request families.
3. `collect_query_result` now sends `session.get(... payload=<CBOR bytes>)` for
   Unit control-plane requests.
4. Dry-run output keeps logical JSON payloads and adds `encoded_payload_hex` for
   diagnostics.
5. Tests prove outgoing payloads are bytes and decode back to the expected
   logical message kind.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`52` tests)
3. `git diff --check` => PASS

### EXEC-159B Unit CBOR Ingress and Core Reply Cutover

`EXEC-159B` moves the Unit runtime boundary onto CBOR bytes for incoming
command/query/update requests and for the core framework reply families. It
keeps the app and update service internals on a JSON-compatible decoded payload
bridge so service boundary refactoring can happen under a narrower follow-up
slice.

Runtime behavior added in this slice:

1. Command, query, and update Zenoh query handlers read binary payload bytes and
   decode CBOR metadata before dispatch.
2. Unit boundary validation now checks decoded metadata structs instead of
   reparsing JSON request text.
3. A generic CBOR request field decoder carries resource, ttl, start args,
   rollback reason, update artifact fields, and callback config fields into the
   internal compatibility payload.
4. Error replies, lease acquire/release replies, query-device replies,
   query-apps replies, and query-leases replies now use CBOR builders and binary
   Zenoh query replies.
5. CLI message-kind selection now differentiates plain app invoke
   `app_command_request` from callback config `callback_config_request` based on
   payload fields.

Verification:

1. `clang-format -i -style=file:applocation/NeuroLink/neuro_unit/.clang-format ...` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`53` tests)
4. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
5. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
6. `git diff --check` => PASS

### EXEC-159C App/Update Reply and Event CBOR Cutover

`EXEC-159C` completes the next runtime CBOR layer for service replies and
framework events. Service ops keep JSON fallbacks for compatibility, but the
runtime now provides binary callbacks and configures binary event publishing.

Runtime behavior added in this slice:

1. App command and update service ops now support optional CBOR query reply
   callbacks in addition to their JSON reply callbacks.
2. Unit runtime wires those callbacks to `neuro_unit_zenoh_query_reply_bytes()`.
3. App command success replies and update prepare/verify/activate/rollback
   success replies prefer CBOR when the callback exists and fall back to JSON
   otherwise.
4. Event infrastructure can be configured with a binary publisher and can
   publish app event payload bytes.
5. Callback events encode as CBOR when binary event publishing is configured.
6. Runtime state/update events now encode CBOR payloads and publish bytes.

Verification:

1. `clang-format -i -style=file:applocation/NeuroLink/neuro_unit/.clang-format ...` => PASS
2. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
3. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, `27` warnings)
4. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
5. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`53` tests)
6. `git diff --check` => PASS

### EXEC-161 Script/Evidence Binary Payload Alignment

`EXEC-161` aligns CLI event collection and evidence output with the CBOR-v2
runtime event cutover. Zenoh event samples are now decoded through the same
binary-aware payload parser used by replies, while CLI stdout and smoke/script
evidence remain JSON/NDJSON with logical field names.

Runtime and evidence behavior added in this slice:

1. Python protocol helpers now expose `parse_wire_payload()` for shared JSON,
   text, and CBOR-v2 payload-object decoding.
2. `append_event_row()` decodes binary CBOR event samples without calling
   `to_string()`, preserving logical JSON payloads for `--output json`, handler
   stdin, and app-callback smoke evidence.
3. JSON event rows include `payload_encoding`; CBOR rows also include
   `payload_hex` for bounded diagnostics.
4. Lease lifecycle events now have a dedicated `lease_event` CBOR message kind
   and `action` key, with Unit and Python schema mirrors synchronized.
5. Unit lease acquire/release lifecycle publishing now prefers CBOR bytes and
   falls back to the legacy JSON publisher only when a binary publisher is not
   configured.
6. Smoke scripts still consume CLI JSON output, so no shell evidence format
   change is required for binary Unit payloads.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`56` tests)
3. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
4. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, `28` warnings)
5. `cd applocation/NeuroLink && git diff --check` => PASS

Remaining release risks:

1. Hardware smoke still needs rerun against a real board after the CBOR event
   evidence alignment.
2. Service internals still use a JSON-compatible decoded request bridge and
   should be revisited during the upcoming extensibility refactor.
3. Golden vectors still need to expand beyond the initial envelope/error reply
   set before release closure.

### EXEC-162A Dispatch Route Classification Refactor

`EXEC-162A` starts the framework extensibility review by separating route
classification from handler dispatch. The runtime handler signatures remain
unchanged, but dispatch now has a structured route result that later slices can
feed into request/reply context and DTO-based service calls.

Architecture behavior added in this slice:

1. `neuro_unit_dispatch_route` now carries a route kind plus optional app id and
   action fields.
2. Command, query, and update paths now use explicit classifier helpers before
   invoking handlers.
3. Fixed lease/query routes are matched through `neuro_protocol` route builders
   rather than ad hoc string construction in the dispatch body.
4. App and update routes are classified with node-scoped prefixes, so a route
   for another node no longer matches through a loose substring search.
5. Nested app/update actions are rejected at classification time, keeping the
   route surface token-based and easier to reason about.

Verification:

1. `clang-format -i ...neuro_unit_dispatch...` => PASS
2. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`neuro_unit_dispatch`: `12` tests)
3. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, `28` warnings)
4. `cd applocation/NeuroLink && git diff --check` => PASS

Remaining release risks:

1. Service calls still receive payload strings and request ids rather than a
   richer request/reply context object.
2. The CBOR-to-internal-JSON compatibility bridge still exists and should be
   narrowed after request DTO ownership is clarified.
3. Hardware smoke and richer golden-vector coverage remain open for closure.

### EXEC-162B Reply Context Metadata Enrichment

`EXEC-162B` continues the framework extensibility review by making the shared
reply context carry the request correlation fields that dispatch already decoded
and validated. This narrows the internal JSON bridge for lease metadata while
keeping app/update service signatures and runtime semantics stable.

Architecture behavior added in this slice:

1. `neuro_unit_reply_context` now carries the transport query, request id, and
   decoded `neuro_request_metadata`, with small accessors for safe fallback use.
2. Dispatch app/update callbacks now receive the decoded metadata object from
   the transport-edge validation path.
3. Runtime app/update adapters populate richer reply contexts before entering
   app command and update services.
4. App command lease checks and update activate/rollback lease checks prefer
   context metadata and only parse JSON payload metadata as a compatibility
   fallback.
5. Reply-context error and lease helper callbacks use the context request id as
   a correlation fallback.
6. Unit tests prove metadata propagation through dispatch and context metadata
   precedence in app/update service lease checks.

Verification:

1. `clang-format -i ...` on touched C/H files => PASS
2. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
3. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, `28` warnings)
4. `cd applocation/NeuroLink && git diff --check` => PASS

Remaining release risks:

1. App/update services still consume JSON-compatible payload strings for
   action-specific fields, so request DTO ownership remains incomplete.
2. Typed result DTO coverage for query/update families still needs follow-up
   before WS-5 is complete.
3. Hardware smoke and richer golden-vector coverage remain open for closure.

### EXEC-162C Request Field Context Bridge Reduction

`EXEC-162C` closes the main EXEC-162 service-boundary refactor by carrying
decoded action-specific request fields through the same dispatch/reply-context
path introduced in `EXEC-162A` and `EXEC-162B`. Services now consume decoded
Unit request fields where available and retain JSON-compatible payload parsing
only as a compatibility fallback.

Architecture behavior added in this slice:

1. `neuro_unit_request_fields` is now a format-neutral Unit request-field DTO
   for decoded resource, ttl, start args, reason, transport, artifact, chunk,
   and callback fields.
2. `neuro_unit_reply_context` now optionally carries request fields alongside
   transport query, request id, and metadata.
3. Runtime CBOR ingress copies decoded CBOR request fields into the Unit request
   DTO before dispatch.
4. Command/update dispatch forwards request fields to app/update runtime handler
   adapters.
5. App command `start` now prefers context `start_args` before JSON fallback.
6. Update prepare/activate/rollback now prefer context transport, chunk size,
   start args, and reason before JSON fallback.
7. Unit tests prove request-field propagation through dispatch and field
   precedence in app/update services.

Verification:

1. `clang-format -i ...` on touched C/H files => PASS
2. `cd /home/emb/project/zephyrproject && west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
3. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, `28` warnings)
4. `cd applocation/NeuroLink && git diff --check` => PASS

Remaining release risks:

1. JSON-compatible payload strings remain for direct service compatibility,
   callback bridge forwarding, lease handlers, and fallback paths.
2. Public API comments and structured diagnostics still need the EXEC-163 pass.
3. Skill packaging, local closure gates, hardware smoke, and release identity
   promotion remain open.

### EXEC-163 Public API Comments and Structured Diagnostics Pass

`EXEC-163` starts WS-6 by documenting the public and EDK-facing Unit interfaces
that stabilized during the CBOR cutover and EXEC-162 service-boundary refactor,
then extends the existing `neuro_unit_diag` framework for bounded protocol,
dispatch, and callback registration diagnostics.

API documentation added in this slice:

1. Reply context comments now describe borrowed transport query ownership,
   decoded metadata/request-field lifetimes, request id fallback behavior, and
   action-field presence semantics.
2. Dispatch comments now describe structured route classification, ops callback
   ownership, synchronous handler lifetimes, and validate/classify/dispatch
   entry-point responsibilities.
3. App-command and update-service comments now describe callback tables, reply
   ownership, synchronous callback expectations, decoded context precedence, and
   JSON fallback behavior.
4. Event and EDK-facing app API comments now describe JSON versus binary event
   publish configuration, caller-owned buffers, return-code expectations, and
   helper DTO lifetimes.
5. Diagnostic API comments now identify the bounded logging helpers available
   for generic context, protocol failures, dispatch outcomes, callback
   registration, update transactions, event publication, and state changes.

Structured diagnostics added in this slice:

1. `neuro_unit_diag_protocol_failure()` logs CBOR ingress/protocol failures with
   route, stage, request id, errno, and payload length without dumping binary
   payload bytes.
2. `neuro_unit_diag_dispatch_result()` logs route classification and dispatch
   outcomes without logging JSON bridge payload contents.
3. `neuro_unit_diag_callback_registration()` logs app callback command
   unsupported/register/enable/enabled stages with app id, command name, and
   return code.
4. Runtime CBOR payload extraction, metadata decode, request-field decode, and
   internal JSON bridge failures now use protocol diagnostics.
5. Dispatch query logs now use bounded debug entries with key, request id, and
   payload length, while route successes/rejections use structured route result
   diagnostics.
6. Callback command registration no longer logs ad hoc register/enable errors;
   it uses the shared callback registration diagnostic helper.

Verification:

1. `clang-format -i ...` on touched C/H files => PASS
2. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
3. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, `30` warnings)
4. `cd applocation/NeuroLink && git diff --check` => PASS

Remaining release risks:

1. WS-6 is not fully closed; protocol codec DTO comments, response/Zenoh
   transport comments, and developer docs for adding commands/events/DTOs remain
   follow-up work.
2. C style still reports warnings even though errors are `0`.
3. Skill packaging, hardware smoke, fuller CBOR golden-vector closure, and
   release identity promotion remain open.

### EXEC-164 Project-Shared Neuro CLI Skill Packaging and Wrapper Upgrade

`EXEC-164` closes the main WS-7 skill-packaging slice by promoting the Neuro CLI
skill into the standard project-shared `.github/skills/neuro-cli/SKILL.md`
discovery path and tightening the automation wrapper around JSON output and
payload status handling.

Skill and wrapper changes in this slice:

1. Added project-shared skill frontmatter with folder-matching `name`, quoted
   keyword-rich `description`, and argument hints for setup, build, preflight,
   smoke, deploy, lease, callback, and evidence workflows.
2. Added progressive-loading resources: workflow reference docs, a callback
   handler template, and a Unit app template.
3. Kept the legacy `neuro_cli/skill` seed as a compatibility pointer while the
   project-shared skill becomes the canonical Agent discovery path.
4. Upgraded `invoke_neuro_cli.py` to enforce JSON-mode invocation and classify
   invalid stdout, nonzero process exits, `ok: false`, `status: error`,
   `status: not_implemented`, and Unit error replies.
5. Surfaced skill path, wrapper path, structured stdout support, and explicit
   audited callback runner policy through `system init`, `system capabilities`,
   and workflow plan JSON.
6. Added regression tests for wrapper command construction, payload-status
   classification, invalid stdout classification, not-implemented mapping, and
   skill frontmatter/resource discovery.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => PASS (`61` tests)

Remaining release risks:

1. Callback runner expansion/audit remains open for `EXEC-165`.
2. Local closure gates, hardware smoke, fuller CBOR golden-vector closure, and
   release identity promotion remain open.
3. Editor skill discovery may require workspace refresh even when the path and
   frontmatter validate.

### EXEC-165 Callback Runner Expansion and Audit Pass

`EXEC-165` expands the explicit opt-in callback/event handler runner into a
release-quality audited subprocess path and applies the same option surface to
the app callback smoke workflow.

Callback runner changes in this slice:

1. Added `--handler-max-output-bytes` to bound retained handler stdout/stderr
   while recording the original stream byte counts and truncation flags.
2. Handler audit records now include argv, constrained cwd, timeout seconds,
   event input byte count, input byte limit, retained stdout/stderr, original
   stdout/stderr byte counts, truncation flags, return code, duration, and
   timeout status.
3. Payload-too-large and handler-cwd failures now return structured audit
   records without executing the handler.
4. JSON event subscription results and app callback smoke results now include a
   top-level `handler_audit` summary with execution count, failure count, and
   status buckets.
5. `app-callback-smoke` now accepts the same explicit handler command/python,
   cwd, timeout, input byte limit, output byte limit, and max-events arguments
   as passive event monitors.
6. Regression tests cover parser support, successful handler audit fields,
   output truncation, large payload rejection, and smoke handler option parsing.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`58` tests)

Remaining release risks:

1. Local closure gates, hardware smoke/deploy/callback evidence, fuller CBOR
   golden-vector closure, and release identity promotion remain open.
2. Handler execution is still intentionally explicit; operators must review the
   local command or Python file before enabling it.

### EXEC-166 Local Closure Gates

`EXEC-166` runs the local pre-hardware closure suite after the CBOR runtime
cutover, service-boundary refactor, project-shared skill packaging, and callback
runner audit work.

Local gate outcomes in this slice:

1. Python compile passed for protocol, CLI, wrapper, and CLI test modules.
2. CLI pytest passed with protocol/CBOR, workflow, skill/frontmatter, wrapper,
   and callback runner coverage.
3. Unit native_sim passed with all current Unit regression suites and test cases.
4. Linux C style passed with `0` errors and `30` warnings.
5. Initial whitespace validation found trailing whitespace/CRLF in files touched
   by the skill-packaging work; those files were mechanically normalized and the
   follow-up `git diff --check` passed.

Verification:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py` => PASS
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => PASS (`63` tests)
3. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`64` suites, `206` test cases)
4. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, `30` warnings)
5. `cd applocation/NeuroLink && git diff --check` => PASS after whitespace normalization

Remaining release risks:

1. Serial-required preflight, Linux smoke, deploy smoke, callback hardware
   evidence, fuller CBOR golden-vector closure, and release identity promotion
   remain open for `EXEC-167`.
2. C style warnings remain non-blocking but should be reviewed during later
   cleanup.

### EXEC-167 Hardware Closure Attempt

`EXEC-167` was started after the local closure gates, but the serial-required
hardware preflight did not pass. Release identity therefore remains at
`RELEASE_TARGET = "1.1.5"` and the Linux smoke, deploy smoke, callback hardware
evidence, and version promotion steps are blocked.

Attempted hardware gate:

1. `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text` => FAIL (`exit 1`, `status=no_reply_board_unreachable`)
2. Board retest: `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text` => FAIL (`exit 1`, serial `/dev/ttyACM0`, router `7447`, `query_device=no_reply`)
3. Direct query confirmation: `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system query device` => FAIL (`exit 2`, `ok=false`, `status=no_reply`, `attempt=3`, `max_attempts=3`)

Observed hardware state:

1. Serial device was present at `/dev/ttyACM0`.
2. The Zenoh router was listening on port `7447`.
3. `query_device` returned `no_reply` with return code `2`.
4. Preflight reported `ready=0`.

Blocker:

1. The host can see the board serial device and router, but the Unit does not
   respond to Neuro CLI `query_device` over Zenoh. Board firmware/network
   readiness or Wi-Fi provisioning must be corrected before smoke/deploy
   closure can continue.

Remaining release risks:

1. Serial-required preflight, Linux smoke, deploy smoke, callback hardware
   evidence, fuller CBOR golden-vector closure, and release identity promotion
   remain open.
2. `RELEASE_TARGET` must not be promoted to `1.1.6` until these gates pass.

### EXEC-167B Hardware Closure and Release Identity Promotion

`EXEC-167B` completed release-1.1.6 hardware closure after the earlier board
no-reply blocker was resolved and after late LLEXT deploy/callback defects were
fixed. Release identity is now promoted to `RELEASE_TARGET = "1.1.6"`.

Closure fixes:

1. Added exact artifact-size validation to deploy prepare and verify so stale or
   truncated LLEXT artifacts cannot be accepted as successful installs.
2. Preserved app command callback fields in CBOR replies, including `echo`,
   `publish_ret`, callback config state, and invoke counts.
3. Added a fresh app build identity, `neuro_unit_app-1.1.6-cbor-v2`, to the
   LLEXT app reply and manifest version `1.1.6` so hardware smoke can prove the
   running app is the new artifact.
4. Added static LLEXT ELF staging to avoid the activation-time large contiguous
   heap allocation that failed with `runtime/load_file RESOURCE_LIMIT cause=-12`.
5. Restored general heap to `57344` while keeping
   `CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576`; reducing heap to
   `40960` prevented Zenoh aux artifact download from reaching `ARTIFACT GET`.
6. Forced `app-callback-smoke` to use live callback subscriber collection so
   hardware callback events are captured during the invoke flow.

Hardware evidence:

1. Unit build: PASS; latest reported DRAM usage was `395152 B (99.01%)`.
2. Unit flash to `/dev/ttyACM0`: PASS.
3. DNESP32S3B prepare for node `unit-01`: PASS.
4. Linux smoke: PASS.
5. Smoke evidence: `smoke-evidence/SMOKE-017B-LINUX-001-20260426-110723.ndjson`.
6. Smoke summary: `smoke-evidence/SMOKE-017B-LINUX-001-20260426-110723.summary.txt`.
7. The smoke evidence includes full Zenoh artifact transfer through the final
   chunk `offset=19456 requested=688 bytes=688` and successful deploy activate.
8. Callback freshness smoke: PASS with
   `--expected-app-echo neuro_unit_app-1.1.6-cbor-v2` and callback handler audit
   execution.

Final local closure checks before release identity promotion:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py` => PASS.
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => PASS (`63` tests before identity promotion and PASS again after updating release-target expectations).
3. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS.
4. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS.
5. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, `22` warnings).
6. `cd applocation/NeuroLink && git diff --check` => PASS.

Fresh LLEXT conclusion:

1. The deploy smoke proves prepare, verify, and activate work with the current
   artifact transfer path.
2. The callback freshness smoke proves the activated LLEXT app is the newly
   built release-1.1.6 app, because the board returned the expected echo
   `neuro_unit_app-1.1.6-cbor-v2` and emitted callback events handled by the
   audited CLI runner.

Remaining risks:

1. C style still reports non-blocking warnings even though the gate exits with
   `0` errors.
2. DNESP32S3B DRAM headroom is tight after CBOR, Zenoh, networking, and LLEXT
   staging work; future features should treat memory budget as a release gate.

### EXEC-158 Extended Unit CBOR DTO Coverage

`EXEC-158` extended Unit-side CBOR-v2 DTO coverage to the remaining major
payload families needed before runtime call-site cutover. Runtime paths still
emit and consume JSON-v2; this slice only adds tested CBOR codec APIs.

Codec coverage added in this slice:

1. Query-apps aggregate replies can encode app count, running count, suspended
   count, and listed app records with runtime, update, artifact, and diagnostic
   fields.
2. Query-leases aggregate replies can encode listed lease records with source,
   priority, resource, lease id, and expiry fields.
3. Update prepare, verify, activate, and rollback replies can encode their
   action-specific success payloads as CBOR-v2 maps.
4. Callback config payloads can decode callback-enabled, trigger-every, and
   event-name fields from CBOR.
5. Update prepare request payloads can decode transport, artifact key, size, and
   chunk size fields from CBOR.
6. Aggregate encoders use a deeper zcbor backup state so canonical nested
   list/map payloads encode reliably under `CONFIG_ZCBOR_CANONICAL`.

Verification:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
2. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`48` tests)
4. `git diff --check` => PASS
5. `build/neurolink_unit_ut_check/zephyr/.config` confirms `CONFIG_NEUROLINK_PROTOCOL_CBOR=y`, `CONFIG_ZCBOR=y`, and `CONFIG_ZCBOR_CANONICAL=y`

### EXEC-157 Basic Unit CBOR DTO Implementation

`EXEC-157` implemented the first Unit-side CBOR-v2 DTO encode/decode coverage
on top of the `EXEC-156` zcbor façade. Runtime Unit/CLI call sites remain on
JSON-v2; this slice only prepares typed CBOR codec paths and vectors.

Codec coverage added in this slice:

1. CBOR encode APIs now exist for error replies, lease replies, query-device
   replies, callback events, and app command replies.
2. Common request metadata can be decoded from CBOR maps, including schema
   version, message kind, request/source/target ids, timeout, priority,
   idempotency key, lease id, forwarded flag, and unknown-key skipping.
3. Envelope decode now scans full typed maps instead of accepting only a two-key
   envelope map, allowing tests and later diagnostics to classify complete CBOR
   payloads by schema version and message kind.
4. Unit tests lock the canonical error reply golden vector and verify metadata
   decode plus malformed/truncated/unsupported payload rejection.
5. The fixture manifest now includes initial vectors for
   `envelope_header.query_request` and `error_reply.not_found`.

Verification:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
2. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors, existing warnings)
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`48` tests)
4. `git diff --check` => PASS