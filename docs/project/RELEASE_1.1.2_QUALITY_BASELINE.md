# NeuroLink Release 1.1.2 Quality Baseline

## 1. Purpose

This document captures the initial quality baseline for release-1.1.2.
It exists to turn code-quality and framework-optimization goals into measurable,
repeatable execution inputs before refactor slices begin.

## 2. Scope of Baseline

Files inspected in this baseline:

1. `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`
2. `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
3. `applocation/NeuroLink/neuro_unit/src/neuro_unit_event.c`
4. `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`

## 3. Collection Method

This baseline used lightweight repository-native inspection rather than new tooling.
Current measurements are intended for prioritization, not formal static-analysis certification.

Commands and methods used:

1. function-start enumeration via regex/line scan
2. approximate function length ranking from declaration line positions
3. include inventory for module-coupling snapshot
4. JSON output call-site count and envelope-shape inspection in `core_cli.py`
5. focused source reads around listener lifecycle and Unit core routing paths

## 4. Baseline Findings

### 4.1 CLI complexity hotspots

Top Python functions by approximate size in `core_cli.py`:

1. `build_parser()` at line 1223, about 281 lines
2. `handle_app_callback_smoke()` at line 1032, about 160 lines
3. `open_session_with_retry()` at line 70, about 94 lines
4. `collect_subscriber_events_threaded()` at line 787, about 93 lines
5. `send_query()` at line 470, about 69 lines
6. `collect_query_result_with_retry()` at line 399, about 59 lines
7. `build_artifact_key()` region starting at line 240, about 55 lines including helper block
8. `subscribe_to_events()` at line 964, about 53 lines
9. `handle_update()` at line 658, about 47 lines
10. `collect_query_result()` at line 360, about 39 lines

Interpretation:

1. Parser construction is oversized and should be split by command family.
2. Listener lifecycle is spread across several medium-large functions with duplicated timing and result concerns.
3. Query/retry and event subscription behavior are mixed with presentation logic.

### 4.2 Unit framework hotspots

Top C functions by approximate size in `neuro_unit.c`:

1. `neuro_unit_connect_once()` at line 1672, about 89 lines
2. `neuro_download_artifact()` at line 512, about 83 lines
3. `neuro_unit_connect_thread()` at line 1761, about 78 lines
4. `update_query_handler()` at line 1458, about 62 lines
5. `handle_lease_acquire()` at line 1137, about 62 lines
6. `neuro_unit_probe_tcp_endpoint()` at line 1613, about 59 lines
7. `neuro_fetch_chunk()` at line 417, about 59 lines
8. `handle_query_apps()` at line 1267, about 59 lines
9. `neuro_unit_start()` at line 1839, about 49 lines
10. `neuro_unit_parse_tcp_endpoint()` at line 1564, about 49 lines

Interpretation:

1. Connection lifecycle remains a concentrated hotspot.
2. Artifact transfer logic still has enough weight to justify another extraction slice.
3. Query routing remains in the main framework file even after earlier modularization.

### 4.3 Coupling baseline

`neuro_unit.c` current include snapshot:

1. Total `#include` lines: 34
2. Project-local headers: 16

Project-local headers currently included:

1. `app_runtime.h`
2. `app_runtime_cmd.h`
3. `app_runtime_exception.h`
4. `neuro_artifact_store.h`
5. `neuro_app_callback_bridge.h`
6. `neuro_app_command_registry.h`
7. `neuro_lease_manager.h`
8. `neuro_recovery_seed_store.h`
9. `neuro_unit.h`
10. `neuro_network_manager.h`
11. `neuro_request_envelope.h`
12. `neuro_request_policy.h`
13. `neuro_unit_app_command.h`
14. `neuro_unit_event.h`
15. `neuro_unit_update_command.h`
16. `neuro_update_manager.h`

Interpretation:

1. `neuro_unit.c` remains a central integration file with high ownership density.
2. The file is acting as both lifecycle coordinator and feature router.
3. The next boundary cleanup should reduce direct dependence on request, update, and app-command details where possible.

### 4.4 Diagnostics baseline

Observed JSON/serialization footprint in `core_cli.py`:

1. `print_json` / `json.dumps` occurrences: 28
2. visible `status` / `reason` style field occurrences: 5

Interpretation:

1. JSON-capable output exists broadly, but envelope shape is not fully normalized.
2. Error handling remains split across command handlers and `main()` fallback logic.
3. Listener and smoke paths should converge on a stable machine-readable result contract.

## 5. First Refactor Candidates

Priority order for release-1.1.2 implementation entry:

1. `core_cli.py:build_parser()`
   - Reason: oversized command registration surface, easy to split with low behavioral risk.
2. `core_cli.py:subscribe_to_events()` plus adjacent listener helpers
   - Reason: listener timing, subscription mode selection, and output shaping are tightly coupled.
3. `core_cli.py:handle_app_callback_smoke()`
   - Reason: long control-flow path mixes orchestration, validation, retry, and result formatting.
4. `neuro_unit.c` connection lifecycle path (`neuro_unit_connect_once`, `neuro_unit_connect_thread`, `neuro_unit_probe_tcp_endpoint`)
   - Reason: clustered complexity in reconnect behavior and transport diagnostics.
5. `neuro_unit.c` artifact-transfer path (`neuro_download_artifact`, `neuro_fetch_chunk`)
   - Reason: high local complexity and likely extraction candidate.

## 6. Proposed Slice Entry

Recommended next executable slice:

1. `EXEC-093`: extract CLI listener lifecycle into smaller helpers with regression-first tests.

Why this should go first:

1. It aligns with both callback reliability and code-quality goals.
2. It has lower blast radius than Unit runtime extraction.
3. It improves the most visible operator-facing behavior while reducing future maintenance cost.

## 7. Validation Baseline Available Before Refactor

Current runnable checks already available in workspace:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py -q`
2. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`

These remain the minimum required gates before and after each release-1.1.2 quality refactor slice.

## 8. Closure Review (2026-04-23)

This quality baseline is now closed against the repository state and the archived
execution evidence gathered during release-1.1.2 implementation.

Acceptance criteria review:

1. Framework decoupling and readability uplift: satisfied.
   - execution ledger closure path spans `EXEC-102` through `EXEC-106` in `applocation/NeuroLink/PROJECT_PROGRESS.md`
   - `neuro_unit.c` orchestration has been thinned through dedicated diagnostics, dispatch, response, and update-service modules
2. Debug and logging coverage expansion: satisfied.
   - update transaction flows now share unified transaction-context logging and Linux operator scripts emit explicit failure classifications for router/serial/readiness paths
3. Linux operator scripts are directly runnable and regression-covered: satisfied.
   - shell regression suite: `applocation/NeuroLink/tests/scripts/run_all_tests.sh`
   - CI anchor: `.github/workflows/neurolink_unit_ut_linux.yml`
4. Executable validation gates for the release are green on the current workspace: satisfied.
   - Linux UT/VM: `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
   - build wrappers: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk` and `--preset unit-app`
   - real-device readiness/smoke: `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh ...` and `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5`
5. Release identity now matches delivered repository state: satisfied.
   - `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` now advertises `RELEASE_TARGET = "1.1.2"`

Residual operational notes:

1. Non-blocking style warning backlog remains outside the scope of this release-closure mark.
2. Real-board Linux smoke still depends on normal operator preconditions such as attached serial hardware, reachable router, and working host-side WSL/network tooling, but those are runtime conditions rather than release-documentation gaps.
