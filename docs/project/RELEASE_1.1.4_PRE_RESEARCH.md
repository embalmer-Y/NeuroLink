# NeuroLink Release 1.1.4 Pre-Research Baseline

## 1. Scope

Release 1.1.4 focuses on architecture re-convergence and code quality across
Neuro Unit and the Neuro CLI after release-1.1.3 closure.

The release objective is not to split files for its own sake. The objective is
to build a robust, complete architecture with clear layer ownership, reduced
coupling, stable use-case boundaries, and easier debugging.

Primary goals:

1. Re-establish clear Neuro Unit layer rules before moving code.
2. Re-converge update application-service ownership so live update execution,
   recovery persistence, runtime actions, events, and replies do not remain
   spread across unclear service/command trampoline layers.
3. Reduce transport leakage from application-layer contracts, especially raw
   Zenoh query types in update/app/dispatch APIs.
4. Normalize diagnostics and debug logging around request/update/app flow
   correlation rather than passing ad hoc log callbacks through every layer.
5. Continue Neuro CLI cleanup only under compatibility guardrails and in support
   of the Unit architecture evidence path.
6. Move Neuro CLI out of `subprojects/` so that `subprojects/` remains reserved
   for Neuro Unit app subprojects.
7. Keep real-board smoke helpers under the canonical `scripts/` surface,
   including the Windows/PowerShell 017B replay helper.
8. Remove legacy application layers once their behavior is fully covered by the
   owning service boundary; release-1.1.4 does not retain a parallel legacy
   update command layer.

Out of scope for kickoff slice:

1. Protocol key/path changes.
2. JSON reply-shape changes.
3. CLI command compatibility breaks, including removal of legacy flat commands
   or existing grouped aliases.
4. Shell command name/help/arity changes.
5. Update state-machine semantic changes.
6. Release identity promotion to `RELEASE_TARGET = "1.1.4"` before closure.

## 2. Current Baseline

Release-1.1.3 is closed in the current workspace with native_sim Unit,
Linux Unit wrapper, unit-app/unit-edk builds, C style, script regression,
canonical preflight, and real-device smoke evidence recorded in:

1. `applocation/NeuroLink/PROJECT_PROGRESS.md`
2. `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
3. `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-043004.ndjson`

The code review for release-1.1.4 planning found that some release-1.1.2 and
release-1.1.3 extractions are useful, but several application-layer boundaries
remain unclear or have become more coupled through wide callback operation
tables.

## 3. Module Classification

### Stable Domain and State Modules

These modules are relatively healthy and should be preserved as reference
boundaries for 1.1.4:

1. `applocation/NeuroLink/neuro_unit/src/neuro_update_manager.c`
   - owns update state transitions and boot reconciliation decisions
   - does not own runtime, transport, reply, or event side effects
2. `applocation/NeuroLink/neuro_unit/src/neuro_lease_manager.c`
   - owns lease table mutation, holder checks, expiry, preemption, and release
3. `applocation/NeuroLink/neuro_unit/src/neuro_artifact_store.c`
   - owns artifact metadata state without direct filesystem or transport work
4. `applocation/NeuroLink/neuro_unit/src/neuro_app_command_registry.c`
   - owns app command descriptor registration and enablement state

### Useful Support Modules

These modules are useful but need guardrails so they do not absorb broader
ownership accidentally:

1. `applocation/NeuroLink/neuro_unit/src/neuro_request_envelope.c`
   - request metadata and simple JSON helper surface
2. `applocation/NeuroLink/neuro_unit/src/neuro_request_policy.c`
   - admission field policy, currently route/action aware
3. `applocation/NeuroLink/neuro_unit/src/neuro_unit_event.c`
   - framework/app event key construction and publish bridge
4. `applocation/NeuroLink/neuro_unit/src/neuro_unit_diag.c`
   - diagnostic context formatting and state/event logging helpers
5. `applocation/NeuroLink/neuro_unit/src/neuro_network_manager.c`
   - network readiness view with port status bridge and Zephyr fallback

### Unclear or Over-Coupled Application Layers

These are the primary 1.1.4 re-convergence targets:

1. `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_service.c`
   - currently owns recovery seed initialization and boot reconciliation
   - delegates live update prepare/verify/activate/rollback into
     `neuro_unit_update_command`
   - acts as an operation-table adapter rather than a full application service
2. `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_command.c`
   - currently owns live update use-case orchestration
   - directly touches update manager, artifact store, runtime load/start/unload,
     app command registry, port filesystem status, events, recovery persistence
     callbacks, logging callbacks, and reply JSON
3. `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_command.c`
   - mixes app registry lookup, lease gate, runtime start/stop/dispatch, state
     event publishing, and reply JSON emission
4. `applocation/NeuroLink/neuro_unit/src/neuro_app_callback_bridge.c`
   - currently a very thin wrapper over `app_runtime_dispatch_command`
   - should either gain a real contract or be folded into app command service

### Transport and Route Adapters

1. `applocation/NeuroLink/neuro_unit/src/zenoh/neuro_unit_zenoh.c`
   - should remain the owner of Zenoh session/queryable/reply/publish mechanics
2. `applocation/NeuroLink/neuro_unit/src/neuro_unit_dispatch.c`
   - currently knows concrete Zenoh route strings and raw query types
   - should be treated as a transport-route dispatcher unless refactored to
     receive parsed route/action tokens from the Zenoh adapter

### Presentation and Composition

1. `applocation/NeuroLink/neuro_unit/src/neuro_unit_response.c`
   - useful JSON response builder surface
   - currently depends broadly on runtime, artifact, update, lease, and network
     structures; 1.1.4 should move it toward formatting DTO-like snapshots or
     service results
2. `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
   - central composition point for globals, service wiring, reply helpers,
     lease/query handlers, dispatch ops, and Zenoh bridge callbacks
   - should become thinner through better application-service contracts, not by
     creating more thin wrappers

## 4. Target Layer Rules

1. Domain/state modules own state transitions and data invariants only.
2. Application services own complete use cases end to end.
3. Transport adapters own Zenoh session/query/reply/sample details only.
4. Presentation modules build JSON from explicit result/snapshot data, not by
   querying arbitrary managers and runtime state themselves.
5. Port adapters own filesystem, network, board, and hardware integration.
6. Diagnostics should be direct shared infrastructure, not an operation-table
   callback that every service must trampoline through.

## 5. Workstreams

### WS-1 Update Application-Service Re-Convergence

1. Promote `neuro_unit_update_service` into the single owner for update use
   cases, or replace it with an equivalent coherent service.
2. Retire `neuro_unit_update_command` as the owner of live update business
   orchestration.
3. Keep `neuro_update_manager` as the pure update state-machine core.
4. Move prepare/verify/activate/rollback/recover coordination under one update
   application boundary:
   - update state transition calls
   - artifact metadata mutation
   - recovery seed snapshot persistence
   - runtime unload/load/start operations
   - app callback command registration after activation or restore
   - update/state event emission
   - service result construction
5. Replace wide command ops tables with narrower request/result or service-port
   contracts as the implementation allows.
6. Remove `neuro_unit_update_command` after the update service owns equivalent
   behavior and test coverage.

### WS-2 Transport and Dispatch Boundary Cleanup

1. Reduce `z_loaned_query_t` exposure from application-service contracts.
2. Either rename/re-scope `neuro_unit_dispatch` as route dispatch or refactor it
   to consume parsed route tokens.
3. Keep `neuro_unit_zenoh` as the only owner of Zenoh reply mechanics.
4. Release-1.1.4 decision: keep `neuro_unit_dispatch` as a transport-route
   adapter where raw `z_loaned_query_t` is allowed, while application services
   remain behind parsed app/action/request data or `neuro_unit_reply_context`.

### WS-3 App Command Service Cleanup

1. Decide whether `neuro_app_callback_bridge` remains a meaningful boundary.
2. Shape `neuro_unit_app_command` as a use-case service with a clear result
   contract rather than transport reply ownership.
3. Preserve `neuro_app_command_registry` as a state/domain module.
4. Release-1.1.4 decision: keep `neuro_app_callback_bridge` as a runtime
   callback adapter only; `neuro_unit_app_command` owns registry lookup, lease
   policy, service-level error mapping, and reply JSON shaping.

### WS-4 Response and Diagnostics Cleanup

1. Keep response JSON shape stable while moving builders toward DTO inputs.
2. Extend diagnostic context for request id, app id, route/action, stage,
   return code, and relevant lease/idempotency identifiers.
3. Normalize update/runtime/zenoh log levels so operator milestones stay visible
   and repeated progress detail moves to debug.

### WS-5 Neuro CLI Quality Track

1. Preserve existing command compatibility.
2. Keep payload-level `status: error` handling as a hard failure contract.
3. Convert callback smoke orchestration into a deterministic step runner.
4. Reduce parser duplication only through compatibility-tested helpers.
5. Rename the host control project from Core/Unit CLI to Neuro CLI and keep its
   canonical project root at `applocation/NeuroLink/neuro_cli`.
6. Keep `applocation/NeuroLink/subprojects` scoped to Neuro Unit application
   subprojects.
7. Keep operator smoke entrypoints discoverable under `applocation/NeuroLink/scripts`.

## 6. Acceptance Criteria

1. Update use-case ownership is coherent: live update and recovery persistence
   no longer live in competing service/command layers.
2. Domain modules remain side-effect light and transport independent.
3. Application-service contracts are narrower and easier to test.
4. Transport-specific query/reply mechanics are isolated to the transport edge.
5. Response and diagnostic code is more consistent without changing public JSON
   payload shape.
6. CLI compatibility and real-device behavior are preserved.
7. Legacy update command code is removed; update command behavior remains
   covered through the update service and response compatibility tests.

## 7. Verification Gates

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`
2. `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q`
4. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
5. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
6. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check`
7. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check`
8. `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text`
9. `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5`

### EXEC-137 Gate Status (2026-04-25)

1. native_sim Unit: PASS before the app/edk include fix (`103/103`) and PASS
   after the include fix for the rebuilt target (`36/36`).
2. Linux Unit wrapper: PASS (`103/103`).
3. Neuro CLI pytest: PASS (`25` tests).
4. C style: PASS (`82` files checked, `0` errors, existing `12` warnings).
5. Script regression: PASS (`7/7`).
6. `unit-app` build: initially FAIL due to missing
   `neuro_unit_diag_update_transaction()` prototype visibility in
   `neuro_unit.c`; PASS after adding `neuro_unit_diag.h`.
7. `unit-edk` build: initially FAIL for the same missing prototype; PASS after
   adding `neuro_unit_diag.h`.
8. Linux preflight: initially BLOCKED by `serial_device_missing` because WSL2
   had not attached the USB serial device; after
   `prepare_dnesp32s3b_wsl.sh --attach-only` attached BUSID `7-4` and exposed
   `/dev/ttyACM0`, the first preflight reached serial but returned `no_reply`.
   After UART board preparation with
   `prepare_dnesp32s3b_wsl.sh --device /dev/ttyACM0 --capture-duration-sec 30`,
   final preflight PASSed with `serial_devices=/dev/ttyACM0` and
   `query_status=ok`.
9. Linux smoke: initially BLOCKED at preflight by the same serial attach issue;
   final smoke PASSed after WSL USB attach and board preparation. Evidence:
   `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-115236.ndjson`.

Hardware closure is complete for the connected board in the current WSL
environment. `EXEC-138` may promote `RELEASE_TARGET` to `1.1.4` after this
evidence is reviewed.

## 8. Initial Execution Slices

1. `EXEC-122`: release-1.1.4 kickoff and architecture re-convergence baseline.
2. `EXEC-123`: add focused update service tests that describe the desired
   prepare ownership before moving code.
3. `EXEC-124`: expand update service tests across verify/activate/rollback
   ownership before moving production code.
4. `EXEC-125`: migrate prepare/verify orchestration into the update service
   boundary while preserving replies and event payloads.
5. `EXEC-126`: migrate activate/rollback orchestration into the update service
   boundary and reduce command ops trampoline usage.
6. `EXEC-127`: introduce or tighten request/reply context contracts to reduce
   raw Zenoh query exposure from application services.
7. `EXEC-128`: revisit app command service and callback bridge ownership.
8. `EXEC-129`: response/diagnostic/log policy cleanup with compatibility tests.
9. `EXEC-130`: Neuro CLI callback smoke/parser/output cleanup under existing
   compatibility tests.
10. `EXEC-131`: rename/move Core CLI project to top-level Neuro CLI and update
   live scripts/docs/tests while preserving CLI behavior and release identity.
11. `EXEC-132`: move the useful Windows/PowerShell 017B smoke replay helper into
   `scripts/` as `smoke_neurolink_windows.ps1` and update live references.
12. `EXEC-133`: remove the legacy `neuro_unit_update_command` layer and add
   response JSON compatibility guardrails before deeper response DTO cleanup.
13. `EXEC-134`: move query-apps response formatting onto explicit app snapshot
   DTO input while preserving the existing manager/runtime compatibility API.
14. `EXEC-135`: decide and document the `neuro_unit_dispatch` boundary as a
   transport-route adapter; raw query stays permitted only at this route edge.
15. `EXEC-136`: keep `neuro_app_callback_bridge` as a runtime adapter and add
   app command service guardrails for registered callback success, dispatch
   failure, and disabled callback command behavior.
16. `EXEC-137`: run release-1.1.4 closure gates across Unit, Neuro CLI, scripts,
   app/edk builds, preflight, and smoke where the environment supports them.
17. `EXEC-138`: promote release identity to `1.1.4` only after closure evidence is
   complete and recorded.

### EXEC-138 Release Identity Promotion (2026-04-25)

`EXEC-138` promoted the canonical Neuro CLI release marker at
`applocation/NeuroLink/neuro_cli/src/neuro_cli.py` from
`RELEASE_TARGET = "1.1.3"` to `RELEASE_TARGET = "1.1.4"` after `EXEC-137`
closure evidence was completed and recorded. The promotion is identity-only:
protocol keys, JSON reply shapes, shell command names, parser aliases, retry
behavior, wire metadata defaults, update state-machine semantics, and firmware
runtime behavior remain unchanged.

The Neuro CLI test suite now locks the capability-map `release_target` field to
`1.1.4`, preserving the release identity as part of the normal CLI regression
gate.

## 9. Risks

1. Update refactoring can regress real-device deploy/activate behavior if state,
   artifact, runtime, and persistence ordering changes.
2. Reducing transport query exposure can accidentally alter reply timing or error
   payload emission.
3. Response DTO cleanup can drift JSON shape unless tests lock current payloads.
4. CLI cleanup can break operator scripts if legacy commands or output envelopes
   change.
5. Over-correction can create another abstraction layer; every new boundary must
   have a clear layer role and test value.
6. Removing the legacy update command layer makes update service tests the single
   behavior guardrail for update routing, prepare metadata, unsupported actions,
   and recover alias handling.

## 10. Rollback Strategy

1. Keep each slice behavior-compatible and independently reversible.
2. Preserve manager/domain modules unless a concrete defect is found.
3. For update service migration, move one phase group at a time and keep tests
   around the previous externally visible behavior.
4. If hardware smoke fails after an architecture slice, rollback that slice before
   broad follow-on refactors.

## 11. Release Identity Policy

`applocation/NeuroLink/neuro_cli/src/neuro_cli.py` now advertises
`RELEASE_TARGET = "1.1.4"`. This promotion was intentionally deferred until
`EXEC-138`, after local, build, script, preflight, and real-board smoke evidence
were complete for `EXEC-137`.