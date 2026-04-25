2026-04-25: Completed release-1.1.4 `EXEC-138` by promoting the canonical Neuro CLI release identity from `RELEASE_TARGET = "1.1.3"` to `RELEASE_TARGET = "1.1.4"` after `EXEC-137` closure evidence completed across local, build, script, preflight, and real-board smoke gates. Added a focused Neuro CLI regression test that locks the capability-map `release_target` field to `1.1.4`, and updated the release-1.1.4 plan to record the final identity promotion. Focused CLI validation passed: pytest `26/26`, `py_compile`, and live capabilities JSON output with `"release_target":"1.1.4"`. Release-1.1.4 is now closed against the current workspace state. — Copilot

#### EXEC-138 Release-1.1.4 Release Identity Promotion

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice updates release identity only; it does not change protocol keys, public JSON payload shape beyond the advertised capability-map `release_target`, shell command names, parser aliases, retry behavior, wire metadata defaults, update state-machine semantics, firmware runtime behavior, or real-device smoke behavior
- Touched files:
  - `applocation/NeuroLink/neuro_cli/src/neuro_cli.py`
  - `applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - promoted `RELEASE_TARGET` from `1.1.3` to `1.1.4` in the canonical Neuro CLI entrypoint
  - added a focused CLI test asserting that `handle_capabilities(..., --output json)` reports `release_target` as `1.1.4`
  - updated the release-1.1.4 plan to mark `EXEC-138` identity promotion complete after `EXEC-137` evidence
- Verification evidence:
  - `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`26` tests)
  - `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py` => PASS
  - `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --output json capabilities` => PASS, emitted `"release_target":"1.1.4"`
- Release closure evidence inherited from `EXEC-137`:
  - native_sim Unit, Linux Unit wrapper, Neuro CLI pytest, C style, script regression, `unit-app`, `unit-edk`, preflight, and Linux smoke all passed after the documented WSL USB attach and board-preparation recovery
  - smoke evidence: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-115236.ndjson`
- Rollback notes:
  - rollback can set `RELEASE_TARGET` back to `1.1.3`, remove the focused `1.1.4` capability-map test, and revert the `EXEC-138` release-plan/progress notes if release ownership decides to reopen 1.1.4 before publication
- Next action:
  - open a new release or maintenance slice for follow-on work rather than extending release-1.1.4

2026-04-25: Completed release-1.1.4 `EXEC-137` closure gate run across local, CLI, script, build, and real-board validation. Local gates passed: native_sim Unit, Linux Unit wrapper, Neuro CLI pytest, C style, and script regression. Build gates initially exposed a real app/edk compile issue: `neuro_unit.c` called `neuro_unit_diag_update_transaction()` without including `neuro_unit_diag.h`; adding the missing include restored both `unit-app` and `unit-edk` builds. Real-board validation initially stopped at `serial_device_missing` because WSL2 had not attached the USB serial device; `prepare_dnesp32s3b_wsl.sh --attach-only` attached BUSID `7-4` and exposed `/dev/ttyACM0`. A first board preflight then reached serial but returned `no_reply`; running `prepare_dnesp32s3b_wsl.sh --device /dev/ttyACM0 --capture-duration-sec 30` prepared the board and reported `NETWORK_READY`. Final real-board preflight and Linux smoke both passed, with smoke evidence recorded at `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-115236.ndjson`. — Copilot

#### EXEC-137 Release-1.1.4 Closure Gates

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice validates release-1.1.4 closure gates and fixes one compile-time declaration issue; it does not change protocol keys, public JSON payload shape, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - added the missing `neuro_unit_diag.h` include to `neuro_unit.c` so app/edk builds see the `neuro_unit_diag_update_transaction()` prototype
  - confirmed the issue was compile-time declaration visibility only; no behavior or public surface changed
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS before the include fix (`103/103`) and PASS after the include fix for the rebuilt target (`36/36`)
  - `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh` => PASS (`103/103`)
  - `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => PASS (`25` tests)
  - `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`82` files checked, `0` errors, existing `12` warnings)
  - `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`7/7`)
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => FAIL before the include fix, then PASS after the include fix
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => FAIL before the include fix, then PASS after the include fix
  - `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text` => initially BLOCKED (`serial_device_missing`; no `/dev/ttyACM*` or `/dev/ttyUSB*`; Zenoh router listening on `7447`; `eclipse-zenoh==1.9.0` satisfied; `build/neurolink_unit/llext/neuro_unit_app.llext` present), then PASS after WSL USB attach and board preparation (`serial_devices=/dev/ttyACM0`, `query_status=ok`)
  - `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5` => initially BLOCKED at preflight with `serial_device_missing`, then PASS after WSL USB attach and board preparation
  - smoke evidence => `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-115236.ndjson`
- Hardware diagnostic evidence:
  - current user is already in `dialout`, so this is not a serial permission failure
  - before attach, only `/dev/ttyS*` devices were visible; no USB serial device was enumerated in the Linux host
  - WSL2 USB attach succeeded through `prepare_dnesp32s3b_wsl.sh --attach-only`, which attached BUSID `7-4` and exposed `/dev/ttyACM0`
  - after attach, preflight reached the serial device but returned `no_reply`; board preparation over UART completed and reported `NETWORK_READY`
- Open risks:
  - real-board closure evidence is now complete for the current connected board and WSL environment; future WSL sessions may require re-running the attach helper if `/dev/ttyACM0` disappears
- Rollback notes:
  - rollback for the code change is limited to removing the `neuro_unit_diag.h` include from `neuro_unit.c`, but that would reintroduce app/edk compile failure
- Next action:
  - proceed to `EXEC-138` release identity promotion now that closure evidence is complete

2026-04-25: Completed release-1.1.4 `EXEC-136` by deciding to keep `neuro_app_callback_bridge` as a runtime callback adapter and strengthening app command service coverage for registered callback commands. The bridge now documents that it owns only app-runtime dispatch and reply-buffer normalization, while `neuro_unit_app_command` owns registry lookup, lease policy, service-level error mapping, and reply JSON. App command tests now cover registered callback success through the bridge, dispatch failure mapping to `500`, and disabled callback command mapping to `409`. Native_sim Unit and C style passed. — Copilot

#### EXEC-136 Release-1.1.4 App Callback Boundary Decision

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice documents and tests internal app callback ownership; it does not change protocol keys, public JSON payload shape, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_app_callback_bridge.h`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_app_runtime_dispatch_mock.h` (new)
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_neuro_app_callback_bridge.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_neuro_unit_app_command.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - kept `neuro_app_callback_bridge` as a meaningful runtime adapter rather than folding it into app command service
  - documented that the bridge owns only `app_runtime_dispatch_command()` invocation and callback reply-buffer normalization
  - documented that `neuro_unit_app_command` owns registered callback registry lookup, lease policy, disabled-command errors, callback dispatch error mapping, and callback reply JSON shaping
  - exposed a test-private app runtime dispatch mock helper so app command service tests can drive callback success/failure without duplicating runtime symbols
  - added app command service coverage for registered callback success through the bridge, callback dispatch failure -> `500`, and disabled callback command -> `409`
  - updated the Unit testing guide with the stronger app command service callback coverage
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
  - `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`82` files checked, `0` errors, existing `12` warnings)
- Open risks:
  - live app callback behavior still depends on real LLEXT app runtime callback implementations; this slice validates service orchestration and bridge behavior with native_sim mocks only
- Rollback notes:
  - rollback can remove the test-private runtime dispatch mock helper, drop the three new app command service callback tests, and remove the ownership comments from the bridge header and release plan
- Next action:
  - continue with `EXEC-137` release-1.1.4 closure gates across Unit, Neuro CLI, scripts, app/edk builds, preflight, and smoke where the environment supports them

2026-04-25: Completed release-1.1.4 `EXEC-135` by deciding and documenting the `neuro_unit_dispatch` boundary as a transport-route adapter rather than refactoring it into a token-only application service. The dispatch layer remains allowed to carry raw `z_loaned_query_t` because it sits directly behind `neuro_unit.c` Zenoh query handlers and owns route matching, metadata policy gating, recovery gate checks, and handoff to service handlers. Application services remain protected behind parsed app/action/request data or `neuro_unit_reply_context`. This closes the WS-2 decision without expanding refactor blast radius. — Copilot

#### EXEC-135 Release-1.1.4 Dispatch Boundary Decision

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice documents an internal architecture boundary decision; it does not change protocol keys, public JSON payload shape, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_dispatch.h`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - reviewed dispatch usage and confirmed it is only used by `neuro_unit.c` and dispatch UTs as a route adapter
  - kept raw `z_loaned_query_t` inside the dispatch surface because dispatch remains transport-route edge code, not application service code
  - documented that application services must receive parsed app/action/request data or `neuro_unit_reply_context`, not dispatch ops directly
  - updated the release-1.1.4 plan to close WS-2 as a boundary decision rather than a tokenization refactor
- Verification evidence:
  - architecture review found no live use of dispatch APIs outside `neuro_unit.c` and dispatch tests
  - no runtime behavior changed in this slice
- Open risks:
  - if future route parsing grows more complex, a parsed-route DTO can still be introduced inside dispatch without changing application service contracts
- Rollback notes:
  - rollback can remove the boundary comment and restore the WS-2 plan text to leave dispatch tokenization undecided
- Next action:
  - continue with `EXEC-136` for app callback bridge/service ownership decision and callback-path coverage

2026-04-25: Completed release-1.1.4 `EXEC-134` by starting the remaining partial-work plan and moving query-apps response formatting toward explicit DTO input. The release-1.1.4 plan now lists `EXEC-134` through `EXEC-138` for response DTO cleanup, dispatch boundary decision, app callback service decision, closure gates, and final release identity promotion. `neuro_unit_response` now exposes `struct neuro_unit_query_app_snapshot`, `struct neuro_unit_query_apps_snapshot`, and `neuro_unit_build_query_apps_snapshot_response()`. The existing `neuro_unit_build_query_apps_response()` API is preserved as a compatibility adapter that extracts runtime/artifact/update-manager state into snapshots before formatting. Exact JSON guardrails cover both the legacy compatibility API and the new snapshot formatter. Native_sim Unit passed and C style passed after formatting. — Copilot

#### EXEC-134 Release-1.1.4 Query Apps Response DTO Entry

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice adds a response DTO entry point and keeps the existing query-apps response API compatible; it does not change protocol keys, public JSON payload shape, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_response.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_response.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_response.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - added explicit query-app snapshot DTO structs for response formatting
  - added `neuro_unit_build_query_apps_snapshot_response()` so the formatter can build JSON from explicit app snapshots instead of directly querying managers
  - kept `neuro_unit_build_query_apps_response()` as the existing compatibility API and changed it to extract snapshots from runtime status, artifact store, and update manager before delegating to the snapshot formatter
  - added an exact JSON contract test for the snapshot formatter and preserved the exact JSON contract for the existing query-apps API
  - updated the release-1.1.4 plan with remaining execution slices for dispatch boundary, callback service decision, closure gates, and release identity promotion
  - updated the Unit testing guide with response module coverage and the query-apps snapshot test
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
  - `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`81` files checked, `0` errors, existing `12` warnings)
- Open risks:
  - only query-apps response formatting has a DTO entry point so far; error, lease, query-device, and query-leases builders remain direct parameter builders, which is acceptable but not a full response DTO conversion
  - hardware smoke was not replayed in this slice; behavior compatibility is covered by native_sim Unit tests only
- Rollback notes:
  - rollback can remove the snapshot DTO structs/function, restore direct query-apps formatting in `neuro_unit_build_query_apps_response()`, and drop the new snapshot response test
- Next action:
  - continue with `EXEC-135` to decide or refine the dispatch boundary, keeping raw Zenoh query mechanics confined to transport-route adapters

2026-04-25: Completed release-1.1.4 `EXEC-133` by removing the legacy `neuro_unit_update_command` layer instead of retaining a parallel command/service implementation. The update service is now the only Unit-side owner of update action orchestration for prepare, verify, activate, rollback/recover, and unsupported update actions. Legacy command guardrails were migrated into `test_neuro_unit_update_service.c`, response JSON builders gained exact compatibility checks for externally visible error, lease, query-device, query-apps, and query-leases payloads, and build targets no longer compile the removed command source. C style and native_sim Unit gates passed. — Copilot

#### EXEC-133 Release-1.1.4 Legacy Update Command Removal

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice removes the legacy internal update command layer and strengthens tests; it does not change protocol keys, public JSON payload shape, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_service.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_response.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_update_command.h` (removed)
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_command.c` (removed)
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_command.c` (removed)
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - removed `neuro_unit_update_command` from production and UT build targets
  - deleted the legacy command header, source, and dedicated command UT file
  - moved command-level prepare guardrails into the update service test by locking artifact key construction, path construction, oversized chunk-size clamping, success reply, update event, and transaction logging behavior
  - added update service unsupported-action coverage for stable `404` reply behavior and no success reply
  - kept recover alias behavior covered through update service tests
  - added exact JSON compatibility assertions for error, lease acquire/release, query device, query apps, and query leases response builders before any future DTO-oriented response cleanup
  - updated the Unit testing guide to remove the legacy command module and reflect the stronger update service/response coverage
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
  - `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`81` files checked, `0` errors, existing `12` warnings)
- Open risks:
  - response builders still consume manager/runtime structures directly; this slice locks JSON compatibility before a future DTO/result cleanup rather than performing that cleanup immediately
  - hardware smoke was not replayed in this slice; behavior compatibility is covered by native_sim Unit tests only
- Rollback notes:
  - rollback can restore the removed command header/source/test files, re-add them to both CMake targets, and remove the migrated update service/response guardrails
- Next action:
  - continue release-1.1.4 response DTO cleanup or closure planning with update orchestration owned only by `neuro_unit_update_service`

2026-04-25: Completed release-1.1.4 `EXEC-132` by classifying the legacy root `SMOKE_017B.ps1` as a still-useful Windows/PowerShell board-smoke helper and moving it into the canonical scripts directory as `applocation/NeuroLink/scripts/smoke_neurolink_windows.ps1`. The script preserves the 017B smoke replay sequence (`query_device`, lease acquire, deploy prepare, verify, activate, monitor events) and writes NDJSON evidence, now through the renamed `neuro_cli.py` entrypoint. Current docs were updated to reference the new path. `pwsh` is not installed in this Linux environment, so PowerShell parser validation could not be run here; old live references to the root `SMOKE_017B.ps1` path were removed. — Copilot

#### EXEC-132 Release-1.1.4 PowerShell Smoke Script Placement

- Status: completed
- Owner: GitHub Copilot with user direction
- Purpose:
  - preserve the Windows/PowerShell version of the 017B real-board smoke replay while moving it out of the project root into the canonical script surface
- Touched files:
  - `applocation/NeuroLink/scripts/smoke_neurolink_windows.ps1` (moved/renamed from `applocation/NeuroLink/SMOKE_017B.ps1`)
  - `applocation/NeuroLink/docs/project/RELEASE_1.0.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_MIGRATION_PLAN.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - identified `SMOKE_017B.ps1` as the Windows/PowerShell counterpart to the Linux real-board smoke path
  - moved it to `scripts/smoke_neurolink_windows.ps1` so root stays clean and all operator scripts live under `scripts/`
  - retained its existing evidence format and smoke step sequence
  - confirmed it already targets `applocation/NeuroLink/neuro_cli/src/neuro_cli.py` after the Neuro CLI relocation
  - updated current documentation references from the old root script path to the new scripts path
- Verification evidence:
  - old root path `applocation/NeuroLink/SMOKE_017B.ps1` no longer exists
  - new script path `applocation/NeuroLink/scripts/smoke_neurolink_windows.ps1` exists
  - live reference scan found no remaining `SMOKE_017B.ps1` references outside historical ledger/evidence context
  - PowerShell parser validation was skipped because `pwsh` is not installed in the current Linux environment
- Open risks:
  - the script was not runtime-replayed because it targets a Windows/PowerShell board-control environment with a default Windows Python path
- Rollback notes:
  - rollback can move `scripts/smoke_neurolink_windows.ps1` back to `SMOKE_017B.ps1` and restore the three documentation references
- Next action:
  - continue release-1.1.4 closure planning with live scripts rooted under `applocation/NeuroLink/scripts`

2026-04-25: Completed release-1.1.4 `EXEC-131` by renaming and relocating the host CLI project from `subprojects/unit_cli` to top-level `neuro_cli`. The canonical CLI entrypoint is now `applocation/NeuroLink/neuro_cli/src/neuro_cli.py`, its tests live under `applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py`, and `applocation/NeuroLink/subprojects` now contains only the Neuro Unit app subproject. Live smoke/preflight/setup scripts and active docs now point to `neuro_cli`; the wire metadata default `--source-core core-cli`, command names, parser aliases, JSON output, retry behavior, and `RELEASE_TARGET = "1.1.3"` were preserved. Validation passed for Neuro CLI unittest, script regression, Python syntax/help, and changed shell syntax. — Copilot

#### EXEC-131 Release-1.1.4 Neuro CLI Relocation

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice changes project layout, file names, live script paths, active docs, and test import names only; it does not change protocol keys, JSON output shape, CLI command names, parser aliases, retry semantics, wire metadata defaults, firmware behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_cli/README.md` (moved from `subprojects/unit_cli`)
  - `applocation/NeuroLink/neuro_cli/requirements.txt` (moved from `subprojects/unit_cli`)
  - `applocation/NeuroLink/neuro_cli/src/neuro_cli.py` (moved/renamed from `subprojects/unit_cli/src/core_cli.py`)
  - `applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py` (moved/renamed from `subprojects/unit_cli/tests/test_core_cli.py`)
  - `applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py` (moved/renamed from `subprojects/unit_cli/scripts/invoke_core_cli.py`)
  - `applocation/NeuroLink/neuro_cli/skill/README.md` (moved from `subprojects/unit_cli`)
  - `applocation/NeuroLink/neuro_cli/skill/SKILL.md` (moved from `subprojects/unit_cli`)
  - `applocation/NeuroLink/scripts/setup_neurolink_env.sh`
  - `applocation/NeuroLink/scripts/preflight_neurolink_linux.sh`
  - `applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`
  - `applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh`
  - `applocation/NeuroLink/tests/scripts/test_preflight_neurolink_linux.sh`
  - `applocation/NeuroLink/SMOKE_017B.ps1`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md`
  - `applocation/NeuroLink/docs/project/DEPLOYMENT_STANDARD.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - created top-level `applocation/NeuroLink/neuro_cli` as the canonical host-control CLI project root
  - moved CLI implementation, tests, wrapper script, requirements, README, and skill docs out of `subprojects/unit_cli`
  - renamed the Python entrypoint from `core_cli.py` to `neuro_cli.py`
  - renamed the unittest file from `test_core_cli.py` to `test_neuro_cli.py` and updated imports/references from `core_cli` to `neuro_cli`
  - renamed the skill wrapper from `invoke_core_cli.py` to `invoke_neuro_cli.py`
  - updated live Linux/PowerShell smoke, preflight, prepare, setup, and script-test paths to the new Neuro CLI location
  - updated active release-1.1.4 plan and deployment/runbook docs to use `neuro_cli` paths
  - updated `setup_neurolink_env.sh` to prefer `--install-neuro-cli-deps` while preserving `--install-unit-cli-deps` as a compatibility alias
  - removed old `applocation/NeuroLink/subprojects/unit_cli`; `applocation/NeuroLink/subprojects` now contains only `neuro_unit_app`
- Verification evidence:
  - `/home/emb/project/zephyrproject/.venv/bin/python -m unittest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py` => PASS (`25` tests, `0` failures, `0` errors)
  - `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`7/7`)
  - `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py` => PASS
  - `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --help` => PASS
  - `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --help` => PASS
  - `bash -n applocation/NeuroLink/scripts/setup_neurolink_env.sh applocation/NeuroLink/scripts/preflight_neurolink_linux.sh applocation/NeuroLink/scripts/smoke_neurolink_linux.sh applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh applocation/NeuroLink/tests/scripts/test_preflight_neurolink_linux.sh` => PASS
- Open risks:
  - historical progress entries, closed release docs, and captured smoke evidence still mention old `subprojects/unit_cli` paths as historical evidence; live scripts/docs/tests now use `neuro_cli`
  - external personal scripts that call the removed `subprojects/unit_cli` path must migrate to `applocation/NeuroLink/neuro_cli/src/neuro_cli.py`
- Rollback notes:
  - rollback can recreate `subprojects/unit_cli`, move `neuro_cli` contents back to the old layout/name, restore live script/doc paths, and remove the `--install-neuro-cli-deps` preferred alias
- Next action:
  - continue release-1.1.4 closure planning on the new canonical Neuro CLI path and keep `subprojects/` reserved for Neuro Unit app subprojects

2026-04-25: Completed release-1.1.4 `EXEC-130` by tightening the Core CLI callback smoke implementation under compatibility tests. The callback smoke path now has explicit helper boundaries for callback invoke key construction, lease-id argument cloning, callback config payload construction, lease acquire payload construction, smoke step collection, and lease cleanup. A success-path smoke test now locks the expected step sequence and JSON output shape. Existing parser aliases, callback config behavior, failure-path smoke output, query retry behavior, CLI command names, and `RELEASE_TARGET = "1.1.3"` were preserved. Core CLI unittest gate passed. — Copilot

#### EXEC-130 Release-1.1.4 Core CLI Callback Smoke Cleanup

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice changes Core CLI internal structure and tests only; it does not change protocol keys, JSON output shape, CLI command names, parser aliases, retry semantics, callback smoke step names, shell behavior, firmware behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`
  - `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - added `app_callback_invoke_key()` so callback config and smoke use the same invoke key construction
  - added `args_with_lease_id()` to replace inline Namespace mutation/copy logic in callback smoke
  - added `build_app_callback_config_payload()` and reused it from both `handle_app_callback_config()` and the smoke flow
  - added `build_app_callback_lease_payload()` to isolate callback smoke lease acquire payload construction
  - added `collect_app_callback_smoke_step()` so smoke step collection has one retry/result/append policy
  - added `release_app_callback_smoke_lease()` so cleanup remains explicit and preserves the `lease_release` step result
  - added `test_handle_app_callback_smoke_runs_success_sequence` to lock subscription, event payload parsing, step ordering, cleanup, and success JSON output
- Verification evidence:
  - `/home/emb/project/zephyrproject/.venv/bin/python -m unittest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` => PASS (`25` tests, `0` failures, `0` errors)
- Open risks:
  - Core CLI remains a single large script; this slice improves callback smoke structure but does not split transport, output, and parser modules yet
  - callback smoke still depends on live Zenoh/Unit behavior for hardware evidence; the unittest guardrails validate parser/output/step orchestration only
- Rollback notes:
  - rollback can inline the helper functions back into `handle_app_callback_config()` and `handle_app_callback_smoke()`, then remove the new success-path smoke test
- Next action:
  - move into release-1.1.4 closure planning: review remaining architecture risks, decide whether to retire/wrap the legacy update command compatibility layer, and keep `RELEASE_TARGET` unchanged until the explicit release closure slice

2026-04-25: Completed release-1.1.4 `EXEC-129` by moving update transaction log formatting into shared diagnostics and adding focused diagnostics tests. `neuro_unit_diag` now owns the `update txn ...` operator-visible log policy through `neuro_unit_diag_update_transaction()`, while `neuro_unit.c` and the update service fallback both delegate to that shared API. The log text, JSON response shapes, CLI behavior, update state-machine semantics, and `RELEASE_TARGET` were preserved. C style and native_sim Unit gates both passed. — Copilot

#### EXEC-129 Release-1.1.4 Diagnostics Log Policy Cleanup

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice changes internal diagnostics ownership only; it does not change protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, operator-visible update transaction log text, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_diag.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_diag.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_service.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_diag.c` (new)
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - added `neuro_unit_diag_update_transaction()` as the shared diagnostics entry point for update transaction logs
  - preserved the existing `update txn app=... action=... phase=... request_id=...` success/warning log text and null-token fallback behavior
  - changed `neuro_unit.c` update transaction callback to delegate to `neuro_unit_diag_update_transaction()` instead of owning log formatting locally
  - changed `neuro_unit_update_service.c` fallback transaction logging to use the same diagnostics API when no external log callback is supplied
  - added `neuro_unit_diag` unit tests for safe context formatting and update transaction null-field tolerance
  - updated the UT guide to include diagnostics tests and coverage estimate
  - normalized touched diagnostic files with the project `.clang-format` style after the style gate identified local formatting/newline drift
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`118/118`, `neuro_unit_diag` `2/2`)
  - `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`84` files checked, `0` errors, existing `12` warnings)
- Open risks:
  - response-builder ownership is still compatible but not fully DTO-only; deeper cleanup should be separate because it can affect query JSON shape if done too aggressively
  - legacy `neuro_unit_update_command.c` still contains duplicate transaction logging paths for its compatibility tests and should be retired or wrapped in a later slice
- Rollback notes:
  - rollback can restore local update transaction log formatting in `neuro_unit.c` and update service fallback, remove `neuro_unit_diag_update_transaction()`, and drop the new diagnostics UT file/source-list entry
- Next action:
  - continue `EXEC-130` with Core CLI callback smoke/parser/output cleanup under existing compatibility tests, keeping release identity at `1.1.3` until the final 1.1.4 closure slice

2026-04-25: Completed release-1.1.4 `EXEC-128` by applying the reply-context boundary discipline to the app command service and adding direct app command service tests. `neuro_unit_app_command.h` no longer exposes `z_loaned_query_t`; app command callbacks and `neuro_unit_handle_app_command()` now use shared `struct neuro_unit_reply_context`, with `neuro_unit.c` remaining the adapter that wraps the Zenoh query pointer for app/update service replies. The callback bridge remains a pure runtime callback adapter. External command JSON, lease behavior, CLI behavior, update state-machine semantics, and `RELEASE_TARGET` were preserved. C style and native_sim Unit gates both passed. — Copilot

#### EXEC-128 Release-1.1.4 App Command Reply Context Boundary

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice changes internal C API shape and UT coverage only; it does not change protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_reply_context.h` (new)
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_update_service.h`
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_app_command.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_service.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_command.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_neuro_unit_app_command.c` (new)
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_service.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - promoted `struct neuro_unit_reply_context` into shared `neuro_unit_reply_context.h` so update service and app command service use the same transport-neutral reply boundary
  - changed `neuro_unit_app_command_ops` and `neuro_unit_handle_app_command()` from raw `z_loaned_query_t` signatures to reply-context signatures
  - updated `neuro_unit_app_command.c` to forward reply context through lease checks, error replies, and success replies without changing action handling or JSON shape
  - updated `neuro_unit.c` to use one set of reply-context adapter wrappers for both app command and update service, keeping Zenoh query mechanics at the outer adapter layer
  - added a focused `neuro_unit_app_command` UT suite covering unsupported app command `404`, runtime start success reply, lease gate invocation, state-event publication, and reply-context forwarding
  - updated the UT guide to list the new app command service tests and coverage estimate
  - normalized touched C/CMake/header/test files to project style and LF endings after the style gate identified local formatting and newline drift
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`116/116`, `neuro_unit_app_command` `2/2`, `neuro_unit_update_service` `7/7`)
  - `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`83` files checked, `0` errors, existing `12` warnings)
- Open risks:
  - `neuro_unit_dispatch.h` and legacy `neuro_unit_update_command.h` still expose raw Zenoh query types; those are now narrower follow-up cleanup targets rather than primary service boundaries
  - app command callback dispatch success/failure through registered callback commands still relies on existing callback bridge tests; deeper app command callback-path service tests can be added when the command compatibility layer is retired
- Rollback notes:
  - rollback can restore app command raw `z_loaned_query_t` signatures, move `struct neuro_unit_reply_context` back into the update service header, remove the new app command UT file/source-list entry, and restore app command ops wiring in `neuro_unit.c`
- Next action:
  - continue `EXEC-129` by cleaning response/diagnostic/log policy ownership with compatibility tests, while preserving JSON shape and operator-visible log semantics

2026-04-25: Completed release-1.1.4 `EXEC-127` by introducing a transport-neutral reply context for the update service boundary. `neuro_unit_update_service.h` no longer exposes `z_loaned_query_t`; update service callbacks and `neuro_unit_update_service_handle_action()` now use `struct neuro_unit_reply_context`, while `neuro_unit.c` remains the adapter that wraps the Zenoh query pointer for reply dispatch. This preserves reply timing, JSON payloads, CLI behavior, update state-machine semantics, and `RELEASE_TARGET` while reducing raw Zenoh type exposure from the update application-service layer. C style and native_sim Unit gates both passed. — Copilot

#### EXEC-127 Release-1.1.4 Update Service Reply Context Boundary

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice changes internal C API shape only; it does not change protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_update_service.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_service.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_service.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - added `struct neuro_unit_reply_context` as the update service reply boundary contract, carrying the transport-specific query as opaque adapter data instead of exposing `z_loaned_query_t`
  - updated update service ops (`reply_error`, `require_resource_lease_or_reply`, and `query_reply_json`) to accept the reply context rather than a raw Zenoh query pointer
  - updated `neuro_unit_update_service_handle_action()` and all service-local update handlers to pass the reply context through unchanged
  - added `neuro_unit.c` adapter wrappers that translate `struct neuro_unit_reply_context` back into the existing Zenoh-backed reply helpers, keeping transport mechanics outside the update service layer
  - updated update service unit tests to use the reply context directly, so those tests no longer depend on `z_loaned_query_t`
  - normalized touched C files with the project `.clang-format` style after the style gate identified local formatting drift
- Verification evidence:
  - `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`81` files checked, `0` errors, existing `12` warnings)
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`114/114`, `neuro_unit_update_service` `7/7`)
- Open risks:
  - `neuro_unit_dispatch.h`, `neuro_unit_app_command.h`, and `neuro_unit_update_command.h` still expose raw Zenoh query types; this slice intentionally narrowed only the now-primary update service boundary
  - `struct neuro_unit_reply_context` currently carries opaque transport data as `const void *`; future work can move it into a shared request/reply context module once dispatch and app command boundaries are ready
- Rollback notes:
  - rollback can restore the update service callbacks and action handler to raw `z_loaned_query_t` signatures, remove the adapter wrappers, and revert the service tests to their previous dummy query pointer usage
- Next action:
  - continue `EXEC-128` by revisiting app command service and callback bridge ownership, applying the same boundary discipline without changing external command behavior

2026-04-25: Completed release-1.1.4 `EXEC-126` by migrating activate/rollback orchestration into `neuro_unit_update_service.c` and removing the service-to-command trampoline from the update service dispatch path. The service layer now directly owns prepare, verify, activate, rollback, recover alias handling, unsupported update-path replies, runtime load/start/unload ordering, callback registry updates, state-event publication, and rollback checkpoint persistence. External JSON payloads, event stages/status values, update state-machine semantics, CLI behavior, and `RELEASE_TARGET` were preserved. C style and native_sim Unit gates both passed. — Copilot

#### EXEC-126 Release-1.1.4 Activate/Rollback Service Ownership Migration

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice changes internal C ownership only; it does not change protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_service.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - moved activate orchestration into the update service, preserving lease validation, runtime unload/load/start ordering, artifact active-state promotion, stable ref recording, recovery seed persistence, callback registration, state-event publication, transaction logs, and success/error replies
  - moved rollback/recover orchestration into the update service, preserving lease validation, rollback checkpoint persistence before destructive work, runtime stop/unload, app command registry cleanup, stable restore handling, artifact cleanup/active-state restoration, state-event publication, transaction logs, and success/error replies
  - removed service construction of `neuro_unit_update_command_ctx` / `neuro_unit_update_command_ops`; `neuro_unit_update_service_handle_action()` now owns all update actions directly and returns the unsupported update-path `404` itself
  - kept `neuro_unit_update_command.c` intact for its existing internal API and unit tests; it can be retired or redirected in a later cleanup once downstream references are reviewed
  - normalized `neuro_unit_update_service.c` with the project `.clang-format` style after the style gate identified local formatting drift
- Verification evidence:
  - `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`81` files checked, `0` errors, existing `12` warnings)
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`114/114`, `neuro_unit_update_service` `7/7`)
- Open risks:
  - `neuro_unit_update_command.c` still contains duplicate update orchestration for compatibility with its direct unit tests; a later cleanup should decide whether to redirect it to the service, reduce it to a thin compatibility wrapper, or retire it from the build
  - real-device activate/rollback behavior should still be covered by the broader hardware smoke chain before release closure because native_sim uses runtime and storage fakes
- Rollback notes:
  - rollback can restore activate/rollback dispatch through `neuro_unit_handle_update_command()` and remove the service-local activate/rollback handlers; service-level tests should catch any external behavior drift during rollback
- Next action:
  - continue `EXEC-127` by tightening request/reply context contracts and reducing raw Zenoh query exposure from application services without changing reply timing or JSON shape

2026-04-25: Completed release-1.1.4 `EXEC-125` by moving prepare/verify update orchestration into `neuro_unit_update_service.c`. The service layer now directly owns prepare and verify state/artifact/persistence/reply/event behavior through `neuro_unit_update_service_handle_action()`, while activate/rollback remain temporarily delegated to `neuro_unit_update_command.c` for the next migration slice. External JSON payloads, event stages/status values, update state-machine semantics, CLI behavior, and `RELEASE_TARGET` were preserved. C style and native_sim Unit gates both passed. — Copilot

#### EXEC-125 Release-1.1.4 Prepare/Verify Service Ownership Migration

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice changes internal C ownership only; it does not change protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_service.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_service.c`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - added direct service-layer prepare handling for update state begin/complete, artifact metadata staging, recovery seed snapshot persistence, update event publication, transaction logging, and success/error replies
  - added direct service-layer verify handling for artifact stat validation, artifact verified-state promotion, update state transition, recovery seed snapshot persistence, update event publication, transaction logging, and success/error replies
  - changed `neuro_unit_update_service_handle_action()` so `prepare` and `verify` are handled by the service before command delegation, preserving service ingress/egress logging around the owned use cases
  - left activate/rollback command delegation intact as an intentional temporary boundary until the next slice, because those paths include runtime load/start/unload and rollback checkpoint ordering
  - normalized the touched C files with the project `.clang-format` style after the style gate identified local formatting drift
  - updated the 1.1.4 pre-research execution slice list to reflect the guardrail-first sequence actually used for `EXEC-123` through `EXEC-125`
- Verification evidence:
  - `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`81` files checked, `0` errors, existing `12` warnings)
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`114/114`)
- Open risks:
  - prepare/verify logic is now service-owned, but command-level prepare/verify code still exists for backward internal API compatibility and should be retired or redirected in a later cleanup once activate/rollback migration is complete
  - activate/rollback still use the command ops trampoline and remain the highest-risk part of the update boundary because they cross runtime control, callback registry updates, state publication, and rollback checkpoint persistence
- Rollback notes:
  - rollback can restore prepare/verify dispatch through `neuro_unit_handle_update_command()` and remove the service-local prepare/verify handlers; external behavior should remain covered by the existing service and command tests
- Next action:
  - continue `EXEC-126` by migrating activate/rollback orchestration into the update service while preserving runtime ordering, rollback checkpoint persistence, callback registration, and reply/event compatibility

2026-04-25: Completed release-1.1.4 `EXEC-124` by expanding update service boundary guardrails across verify, activate, and rollback before production migration. The service test suite now drives the full prepare -> verify -> activate -> rollback success path through `neuro_unit_update_service_handle_action()`, including artifact verification, active-state promotion, callback/state-event publication, rollback recovery semantics, and checkpoint persistence via a local recovery seed fake FS. The native_sim Unit gate passed with the update service suite at `7/7` and all reported tests passing. — Copilot

#### EXEC-124 Release-1.1.4 Update Service Full-Flow Guardrail Tests

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice is test/documentation only; it does not change production C behavior, protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_service.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - added service-level verify coverage proving the service entry moves a prepared app to verified state, marks artifact metadata verified, emits a success reply, and ends at service egress
  - added service-level activate coverage proving the service entry promotes a verified app to active state, marks artifact metadata active, registers the callback command, publishes a state event, and emits the activate event
  - added service-level rollback coverage proving the service entry completes the recovery flow from active to rolled back, emits success reply/event/state notifications, and preserves the recover transaction label
  - added local port FS and recovery seed fake FS support in the service tests so artifact stat and rollback checkpoint persistence are verified without board storage
  - updated the UT guide to list the expanded `neuro_unit_update_service` matrix and revised service-entry coverage estimate
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`neuro_unit_update_service` `7/7`; reported total `110/110`)
- Open risks:
  - production update orchestration is still physically implemented in `neuro_unit_update_command.c`; the tests now protect the desired service boundary but the code migration has not yet occurred
  - rollback depends on checkpoint persistence before destructive unload/restore work, so the production migration must preserve the current checkpoint ordering exactly
- Rollback notes:
  - rollback can remove the new service full-flow tests, the local fake FS helpers, the UT guide additions, and this ledger entry without affecting production firmware behavior
- Next action:
  - start `EXEC-125` by moving prepare/verify orchestration ownership from `neuro_unit_update_command.c` into `neuro_unit_update_service.c` under the new service-level tests, keeping external JSON and CLI behavior unchanged

2026-04-25: Completed release-1.1.4 `EXEC-123` by adding update service boundary guardrails before production code migration. The new and strengthened UT coverage treats `neuro_unit_update_service_handle_action()` as the externally relevant application-service entry: prepare now asserts staged artifact metadata, prepared update state, success reply, update event publication, and service egress logging; repeated prepare is explicitly documented as preserving the current state-machine semantics rather than introducing a behavior change. The native_sim Unit gate passed (`240/240`). — Copilot

#### EXEC-123 Release-1.1.4 Update Service Boundary Guardrail Tests

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice is test/documentation only; it does not change production C behavior, protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_service.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - strengthened the prepare service test so future refactors must keep service-level ownership visible at the boundary: artifact staging, requested transport preservation, runtime artifact path, prepared update state, success reply, update event publication, and final egress logging
  - added a repeated-prepare service test that locks the current compatible behavior: no error reply, two success replies, prepared state retained, and service egress preserved
  - captured update event fields in the service test mocks so service-level event assertions are direct rather than count-only
  - updated the UT guide to list `neuro_unit_update_service` as its own coverage target and document the current service test cases
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`240/240`)
- Open risks:
  - these tests are guardrails for the prepare path and service entry behavior; verify/activate/rollback orchestration still needs service-level tests before moving their production code out of the command layer
  - current repeated prepare semantics are preserved intentionally; any future decision to make duplicate prepare a conflict must be a deliberate state-machine contract change with release notes and broader tests
- Rollback notes:
  - rollback can remove the new service test assertions, the repeated-prepare test, the UT guide additions, and this ledger entry without affecting production firmware behavior
- Next action:
  - continue `EXEC-124` by adding service-level verify/activate/rollback tests, then migrate update orchestration from `neuro_unit_update_command.c` toward `neuro_unit_update_service.c` without changing external JSON or CLI behavior

2026-04-25: Started release-1.1.4 implementation with `EXEC-122`, opening the architecture re-convergence track from the closed release-1.1.3 baseline. The kickoff deliberately reframes the quality work away from file splitting as a success metric and toward durable layer contracts: stable domain/state modules, coherent application services, isolated transport adapters, narrower response/diagnostic ownership, and CLI compatibility. Created `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md` with module classification, target layer rules, workstreams, acceptance criteria, verification gates, initial execution slices, and release identity policy. — Copilot

#### EXEC-122 Release-1.1.4 Architecture Re-Convergence Baseline Kickoff

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this kickoff records release-1.1.4 architecture direction and execution baseline only; it does not change protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, firmware runtime behavior, or `RELEASE_TARGET`
- Touched files:
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md` (new)
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - opened release-1.1.4 as an architecture re-convergence release rather than a broad file-splitting cleanup
  - recorded the corrected module baseline: `neuro_update_manager`, `neuro_lease_manager`, `neuro_artifact_store`, and `neuro_app_command_registry` are treated as stable domain/state modules, while update service/command, app command, dispatch, response, and diagnostics are the primary contract-cleanup areas
  - set the first implementation target as update application-service ownership re-convergence so live update execution and recovery persistence move toward one coherent boundary
  - preserved release identity policy: `core_cli.py` remains at `RELEASE_TARGET = "1.1.3"` until the 1.1.4 closure slice promotes it with evidence
- UT added or updated:
  - no source-level UT changes in this kickoff slice
  - next slice should add focused update service tests before moving live update orchestration
- Verification evidence:
  - pre-research baseline document created: `applocation/NeuroLink/docs/project/RELEASE_1.1.4_PRE_RESEARCH.md`
- Open risks:
  - the highest-risk implementation area is the update service/command boundary because it currently crosses update manager state, artifact metadata, runtime load/start/unload, recovery seed persistence, event publishing, and query replies
  - future slices must avoid replacing one callback trampoline with another abstraction layer that lacks a clear layer role
- Rollback notes:
  - rollback can remove the new pre-research document and this ledger entry without affecting runtime behavior
- Next action:
  - start `EXEC-123` by adding focused update service tests that lock the desired prepare/verify/activate/rollback ownership before code migration

2026-04-25: Closed release-1.1.3 after completing the architecture/quality track and restoring real-device Linux evidence. Promoted `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` to `RELEASE_TARGET = "1.1.3"`, appended the closure review to `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`, and confirmed the release evidence chain: C style gate PASS, native_sim Unit PASS, Linux Unit wrapper PASS, unit-app/unit-edk builds PASS, script regression suite PASS (`7/7`), canonical preflight PASS, and real-device smoke PASS with evidence `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-043004.ndjson`. Release-1.1.3 is now closed; follow-on work should open a new release or maintenance slice rather than extend this one. — Copilot

Release-1.1.3 development status: completed.

#### EXEC-121 Release-1.1.3 Closure Review and Release Target Promotion

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice closes release-1.1.3 and updates release identity; it does not change protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, or firmware runtime behavior
- Touched files:
  - `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Closure summary:
  - release-1.1.3 architecture/quality objectives are satisfied: port filesystem/network contracts are in place, shell ownership is separated with an extension surface, zenoh transport helpers are extracted, runtime command legacy hooks are removed, and real-device evidence is restored
  - promoted Unit CLI release identity to `RELEASE_TARGET = "1.1.3"`
  - recorded a release-1.1.3 closure review with acceptance criteria, evidence, residual notes, and follow-up boundaries
- Verification evidence:
  - Unit CLI tests: `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py -q` => PASS
  - script regression suite: `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`7/7`)
  - real-device smoke evidence already captured in `EXEC-120`: `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5` => PASS (`result=PASS`, evidence `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-043004.ndjson`)
- Residual notes:
  - lab Wi-Fi fallback defaults remain local-test convenience and should be overridden for non-lab deployments
  - opaque Unit query/reply context, deeper `app_runtime_cmd` rename/extraction, and DNESP32S3B provider-specific endpoint probe remain follow-up candidates
- Rollback notes:
  - rollback can set `RELEASE_TARGET` back to `1.1.2` and remove this closure section if release ownership decides to reopen 1.1.3 before publication
- Next action:
  - open a new release or maintenance slice for any follow-on work

2026-04-25: Continued release-1.1.3 hardware closure with `EXEC-120`, adding lab Wi-Fi defaults to the DNESP32S3B WSL preparation helper and restoring real-device evidence. `prepare_dnesp32s3b_wsl.sh` now falls back to the validated lab SSID/credential when command-line arguments and environment variables are not provided, while still allowing explicit overrides. Running the helper without Wi-Fi arguments prepared `/dev/ttyACM0`, brought the board to `NETWORK_READY`, and canonical preflight returned `ready=1`; the real-device smoke then passed with fresh evidence `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-043004.ndjson`. — Copilot

#### EXEC-120 Release-1.1.3 Lab Wi-Fi Defaults and Real-Device Smoke Recovery

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice changes Linux/WSL operator-script defaults only; it does not change firmware protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, or runtime code
- Touched files:
  - `applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Implementation summary:
  - added validated lab Wi-Fi fallback defaults to `prepare_dnesp32s3b_wsl.sh`
  - preserved override precedence: command-line arguments override `NEUROLINK_WIFI_SSID` / `NEUROLINK_WIFI_CREDENTIAL`, which override `NEUROLINK_DEFAULT_WIFI_SSID` / `NEUROLINK_DEFAULT_WIFI_CREDENTIAL`, which override the lab defaults
  - updated helper usage text to call out the lab-default fallback behavior without requiring operators to pass Wi-Fi arguments for the current test bench
- Verification evidence:
  - default help path: `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --help | grep -F 'lab default'` => PASS
  - script regression suite: `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`7/7`)
  - board preparation with defaults: `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --busid 7-4 --capture-duration-sec 30` => PASS (`serial_device=/dev/ttyACM0`, `network_state=NETWORK_READY`, `query_status=ok`)
  - canonical preflight: `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text` => PASS (`ready=1`, `query_status=ok`, `serial_devices=/dev/ttyACM0`)
  - real-device smoke: `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5` => PASS (`result=PASS`, evidence `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-043004.ndjson`)
- Open risks:
  - the lab-default credential is intentionally stored for local test convenience; deployments outside this bench should pass explicit Wi-Fi values or environment overrides
- Rollback notes:
  - rollback can restore empty Wi-Fi defaults and require explicit `--wifi-ssid` / `--wifi-credential` or environment variables again
- Next action:
  - use the fresh real-device evidence when making the release-1.1.3 closure call

2026-04-25: Continued release-1.1.3 hardware-gate recovery with `EXEC-119`, diagnosing the post-attach preflight failure and improving the DNESP32S3B WSL preparation helper. The board USB serial adapter was visible to Windows as CH343 BUSID `7-4` but initially only `Shared`; attaching it into WSL exposed `/dev/ttyACM0`. With serial present, preflight advanced from `serial_device_missing` to `no_reply_board_unreachable`; UART diagnostics showed the shell is responsive and the `app` command surface is present, but network readiness still requires board Wi-Fi preparation. Added `prepare_dnesp32s3b_wsl.sh --attach-only` so operators can attach/detect USB serial without supplying Wi-Fi credentials or running the full setup flow, and sharpened the preflight no-reply detail to point at UART network readiness / Wi-Fi preparation. — Copilot

#### EXEC-119 Release-1.1.3 DNESP32S3B WSL Attach Recovery and Preflight Diagnosis

- Status: completed for environment-script enhancement; board network preparation remains pending
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice changes Linux/WSL operator scripts and diagnostics only; it does not change firmware protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, or runtime code
- Touched files:
  - `applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh`
  - `applocation/NeuroLink/scripts/preflight_neurolink_linux.sh`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Diagnosis summary:
  - Windows/usbipd saw the board as `USB-Enhanced-SERIAL CH343 (COM4)` on BUSID `7-4` in `Shared` state
  - Linux initially had no `/dev/ttyACM*` or `/dev/ttyUSB*`; `usbipd.exe attach --wsl --busid 7-4` exposed `/dev/ttyACM0`
  - preflight then failed as `no_reply_board_unreachable` rather than `serial_device_missing`, proving serial attachment was fixed while board/router queryability remains blocked
  - UART capture confirmed the shell is responsive and `app` root commands are present; earlier `app status` failure was not reproduced after command-list capture
  - UART logs still showed network not ready (`ADAPTER_READY`, `iface_up=0`, `ipv4=no-ipv4`), so the next operational step is Wi-Fi preparation through `prepare_dnesp32s3b_wsl.sh` with credentials
- Implementation summary:
  - added `--attach-only` to `prepare_dnesp32s3b_wsl.sh` so USB attach/serial detection can run without Wi-Fi SSID/credential requirements
  - moved Wi-Fi credential validation after serial attach and after the attach-only exit path
  - updated preflight `no_reply_board_unreachable` detail to direct operators toward UART network readiness checks or `prepare_dnesp32s3b_wsl.sh` with Wi-Fi credentials
- Verification evidence:
  - attach helper help: `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --help | grep -F -- '--attach-only'` => PASS
  - attach-only path: `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --attach-only --busid 7-4` => PASS (`serial_device=/dev/ttyACM0`)
  - script regression suite: `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`7/7`)
  - canonical preflight: `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text` => expected FAIL (`status=no_reply_board_unreachable`, `query_status=no_reply`)
- Open risks:
  - real-device smoke remains blocked until the board is configured onto the network and `query device` replies through zenoh
  - current shell environment does not define `NEUROLINK_WIFI_SSID` or `NEUROLINK_WIFI_CREDENTIAL`, so full preparation cannot be run non-interactively yet
- Rollback notes:
  - rollback can remove `--attach-only` and restore Wi-Fi validation before attach; the preflight detail text can revert without firmware impact
- Next action:
  - provide Wi-Fi credentials via `NEUROLINK_WIFI_SSID` / `NEUROLINK_WIFI_CREDENTIAL` or pass them to `prepare_dnesp32s3b_wsl.sh`, then rerun preflight and smoke

2026-04-25: Continued release-1.1.3 closure-tail execution with `EXEC-118`, checking the real-device gate and recording the remaining closure decisions. The hardware/router preflight reached a listening router but failed because no serial device was visible on the Linux host, so smoke was not run and release-1.1.3 remains not fully closed on real-device evidence. Opaque Unit query/reply context, deeper `app_runtime_cmd` rename/extraction, and DNESP32S3B provider-specific endpoint probe are recorded as follow-up candidates rather than late release-1.1.3 scope additions. — Copilot

#### EXEC-118 Release-1.1.3 Closure Decision and Hardware Gate Check

- Status: completed for decision recording; release real-device closure remains pending
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice records closure decisions and hardware evidence state only; it does not change protocol keys, JSON payloads, shell command names, CLI behavior, update state-machine semantics, or runtime code
- Touched files:
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Closure decisions:
  - opaque Unit query/reply context remains a follow-up candidate until transport tests are expanded beyond the current zenoh wrapper coverage
  - deeper `app_runtime_cmd` renaming or extraction remains a follow-up candidate because the current post-legacy-hook state is an acceptable thin facade
  - DNESP32S3B provider-specific `probe_endpoint` should not land without hardware replay; keep the existing socket fallback until lab evidence is available
- Verification evidence:
  - hardware/router preflight: `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text` => FAIL (`status=serial_device_missing`, `router_listening=1`, `serial_present=0`, no `/dev/ttyACM*` or `/dev/ttyUSB*` visible)
  - real-device smoke: not run because preflight did not reach ready state
- Open risks:
  - release-1.1.3 cannot be marked fully closed against real-device behavior until serial hardware is attached/visible and preflight plus smoke pass
- Rollback notes:
  - documentation-only entry; no code rollback required
- Next action:
  - attach or pass through the DNESP32S3B serial device to the Linux host, rerun preflight, then run `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5` when preflight reports ready

2026-04-25: Continued release-1.1.3 implementation with `EXEC-117`, adding a public shell extension surface for the existing `app` command root. The shell module now exposes wrappers for section-backed app subcommand set creation and command registration, preserving all existing command syntax, help text, handlers, and arity while allowing future board/provider shell commands to attach from separate files. — Copilot

#### EXEC-117 Release-1.1.3 Shell Extension Surface

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice stays inside release-1.1.3 architecture/refactor scope: shell command names, help strings, arity, visible output intent, protocol keys, JSON payloads, CLI behavior, and update state-machine semantics are unchanged
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/shell/neuro_unit_shell.h`
  - `applocation/NeuroLink/neuro_unit/include/shell/neuro_unit_shell_internal.h`
  - `applocation/NeuroLink/neuro_unit/src/shell/neuro_unit_shell.c`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - introduced `shell/neuro_unit_shell.h` as the public shell extension header
  - defined `NEURO_UNIT_SHELL_APP_PARENT` as `(app)` plus wrappers around `SHELL_SUBCMD_SET_CREATE`, `SHELL_SUBCMD_ADD`, and `SHELL_SUBCMD_COND_ADD`
  - updated the internal shell header to include the public shell extension header instead of depending directly on Zephyr shell internals
  - converted the existing `app` command table from a local static subcommand array to section-backed app subcommand registration entries
  - preserved every existing app command syntax, help string, handler, mandatory argument count, and optional argument count
- UT added or updated:
  - none; this slice is a registration-surface refactor covered by style, build/link, native_sim, and script regression gates
- Verification evidence:
  - C style gate: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`81` files checked, `0` errors, existing `12` warnings)
  - app build path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS; generated ESP32-S3 image and `llext-edk.tar.xz`
  - native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
  - Linux Unit wrapper: `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh` => PASS (`PROJECT EXECUTION SUCCESSFUL`, `result=PASS`)
  - unit-app build path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS (`Built target neuro_unit_app`)
  - script regression suite: `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`script_tests_passed=7`, `script_tests_failed=0`)
- Open risks:
  - no hardware/router preflight or smoke replay was run in this slice; real-device shell/zenoh evidence remains a release closure risk until lab state is available
- Rollback notes:
  - rollback can restore the local `SHELL_STATIC_SUBCMD_SET_CREATE(sub_app, ...)` table in `src/shell/neuro_unit_shell.c` and remove the public shell extension header
- Next action:
  - decide whether release-1.1.3 closure needs hardware preflight/smoke replay before marking the release fully closed, or explicitly scope that evidence out with a documented risk

2026-04-25: Continued release-1.1.3 implementation with `EXEC-116`, splitting the UART shell command handlers by responsibility while preserving the existing command surface. Shell registration now stays in the shell module entry file, lifecycle/status, storage, network, and zenoh connect override handlers live in dedicated submodules, and runtime remains focused on LLEXT app lifecycle implementation. — Copilot

#### EXEC-116 Release-1.1.3 Shell Command Responsibility Split

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice stays inside release-1.1.3 architecture/refactor scope: shell command names, help strings, arity, visible output intent, protocol keys, JSON payloads, CLI behavior, and update state-machine semantics are unchanged
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/shell/neuro_unit_shell_internal.h`
  - `applocation/NeuroLink/neuro_unit/src/shell/neuro_unit_shell.c`
  - `applocation/NeuroLink/neuro_unit/src/shell/neuro_unit_shell_lifecycle.c`
  - `applocation/NeuroLink/neuro_unit/src/shell/neuro_unit_shell_storage.c`
  - `applocation/NeuroLink/neuro_unit/src/shell/neuro_unit_shell_network.c`
  - `applocation/NeuroLink/neuro_unit/src/shell/neuro_unit_shell_zenoh.c`
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - introduced `shell/neuro_unit_shell_internal.h` for shared shell helpers and command handler declarations
  - reduced `src/shell/neuro_unit_shell.c` to shared guard/reporting helpers and `SHELL_CMD_REGISTER()` command table ownership
  - moved app lifecycle/status handlers into `neuro_unit_shell_lifecycle.c`
  - moved storage mount/unmount/list handlers into `neuro_unit_shell_storage.c`
  - moved network connect/disconnect handlers into `neuro_unit_shell_network.c`
  - moved zenoh connect override show/set/clear handlers into `neuro_unit_shell_zenoh.c`
- UT added or updated:
  - none; this slice is a structure-preserving shell module split and is covered by app build/link plus native_sim regression
- Verification evidence:
  - native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`110/110` tests across `18` suites)
  - C style gate: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`80` files checked, `0` errors, existing `11` warnings only)
  - app build path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS; generated ESP32-S3 image and `llext-edk.tar.xz`
- Open risks:
  - no shell behavior replay was run in this slice; command shape was preserved by keeping the existing registration names/help/arity while validating compile/link
- Rollback notes:
  - rollback can merge the split command handlers back into `src/shell/neuro_unit_shell.c` and remove the added shell submodules from `CMakeLists.txt`
- Next action:
  - continue release-1.1.3 within the refactor boundary by choosing the next narrow structure slice, likely board/provider probe ownership or further `neuro_unit.c` handler ownership cleanup

2026-04-25: Continued release-1.1.3 implementation with `EXEC-115`, moving endpoint probe ownership to the port network contract without expanding release scope. Zenoh session open and aux-session open now call `neuro_unit_port_network_ops.probe_endpoint()` when a provider supplies it, while preserving the existing socket-based TCP probe fallback and all public protocol behavior. — Copilot

#### EXEC-115 Release-1.1.3 Port Network Endpoint Probe Bridge

- Status: completed
- Owner: GitHub Copilot with user direction
- Release boundary note:
  - this slice stays inside release-1.1.3 architecture/refactor scope: no protocol keys, JSON payloads, shell command names, CLI behavior, or update state-machine semantics are changed
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/zenoh/neuro_unit_zenoh.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/port/test_neuro_network_manager_port.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - made `neuro_unit_zenoh_probe_tcp_endpoint()` delegate to `neuro_unit_port_network_ops.probe_endpoint()` when the active provider exposes a probe hook
  - preserved the original zenoh socket/DNS TCP probe as the fallback path when no port hook is registered
  - kept DNESP32S3B behavior unchanged in this slice by not wiring a board-specific probe implementation yet
  - added native_sim port contract coverage proving probe endpoint callback registration and argument forwarding
- UT added or updated:
  - added `test_network_ops_forward_probe_endpoint`
- Verification evidence:
  - native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`110/110` tests)
  - C style gate: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`75` files checked, `0` errors, existing warnings only)
  - app build path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
- Open risks:
  - DNESP32S3B still uses the preserved zenoh socket fallback for endpoint probe until a board/provider-specific probe hook is implemented and hardware-replayed
- Rollback notes:
  - rollback can remove the port hook branch in `neuro_unit_zenoh_probe_tcp_endpoint()` and keep the socket fallback as the only implementation
- Next action:
  - continue release-1.1.3 by either adding a DNESP32S3B provider probe hook after hardware replay planning, or by splitting `src/shell/neuro_unit_shell.c` command ownership by responsibility

2026-04-25: Continued release-1.1.3 implementation with `EXEC-114`, wiring network status collection into the port network contract. `neuro_network_manager` now prefers `neuro_unit_port_network_ops.get_status()` when provided, DNESP32S3B publishes Wi-Fi interface/link/IP status through the port ops table, and native_sim tests cover ready, unsupported transport, and provider-error status mapping. — Copilot

#### EXEC-114 Release-1.1.3 Port Network Status Bridge

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_network_manager.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic_dnesp32s3b.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/port/test_neuro_network_manager_port.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - made `neuro_network_manager_collect_status()` prefer `neuro_unit_port_network_ops.get_status()` and preserve the existing Zephyr network fallback when no port hook is registered
  - added DNESP32S3B network status publication for interface index/name, interface-up state, Wi-Fi link readiness, and IPv4 address
  - guarded the direct Zephyr network fallback so native_sim tests without `CONFIG_NETWORKING` link cleanly while port-hook tests still execute
  - added native_sim coverage for ready status mapping, unsupported transport classification, and provider error propagation
- UT added or updated:
  - added `test_collect_status_uses_port_ready_state`
  - added `test_collect_status_rejects_bad_transport`
  - added `test_collect_status_propagates_port_error`
- Verification evidence:
  - native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`109/109` tests)
  - C style gate: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`75` files checked, `0` errors, existing warnings only)
  - app build path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS; prior `neuro_network_manager` truncation warning removed
- Open risks:
  - `probe_endpoint` remains in the port network ops contract but is not wired in this slice; TCP endpoint probe behavior still lives in the zenoh helper module
  - DNESP32S3B link readiness is currently based on Wi-Fi connect/disconnect events and should be replayed on hardware before final release closure
- Rollback notes:
  - rollback can remove the network-manager port hook branch and DNESP32S3B `get_status` callback while keeping connect/disconnect port ops unchanged
- Next action:
  - continue release-1.1.3 by deciding whether endpoint probe should move behind `neuro_unit_port_network_ops.probe_endpoint` or by splitting shell command ownership by responsibility

2026-04-25: Continued release-1.1.3 implementation with `EXEC-113`, thinning the runtime command configuration surface now that storage/network dispatch is covered through port ops. `app_runtime_cmd_config` no longer carries legacy `storage_ops` or `network_ops` hook structs; it now expresses command support, runtime lifecycle callbacks, and persistence paths only. — Copilot

#### EXEC-113 Release-1.1.3 Runtime Command Config Legacy Hook Removal

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - removed the unused `app_runtime_storage_ops` and `app_runtime_network_ops` structs from the public runtime command header
  - removed `storage_ops` and `network_ops` fields from `app_runtime_cmd_config`
  - removed the now-empty legacy hook initializers from `app_runtime_cmd.c`
  - preserved command capability gates, runtime lifecycle callbacks, app artifact path, and recovery seed path semantics
- UT added or updated:
  - no new tests in this slice; `EXEC-112` already added storage/network port-dispatch coverage that made the compatibility fields removable
- Verification evidence:
  - native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`106/106` tests)
  - C style gate: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`74` files checked, `0` errors, existing warnings only)
  - app build path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
- Open risks:
  - external downstream code that still initializes removed config fields will need to move to `neuro_unit_port_set_fs_ops()` / `neuro_unit_port_set_network_ops()` or board provider callbacks
- Rollback notes:
  - rollback can reintroduce the two legacy structs and config fields without changing runtime command dispatch behavior
- Next action:
  - continue release-1.1.3 by expanding network port status/probe hooks and tests, or by further splitting `src/shell/neuro_unit_shell.c` command ownership by responsibility

2026-04-25: Continued release-1.1.3 implementation with `EXEC-112`, adding focused native_sim coverage for the port filesystem contract and runtime storage-command dispatch through port FS ops. The new suite locks down fs-op registration/reset and path validation, while runtime capability tests now prove storage mount/unmount use `neuro_unit_port_fs_ops` instead of legacy config hooks. — Copilot

#### EXEC-112 Release-1.1.3 Port Filesystem Contract Unit Coverage

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/port/test_neuro_unit_port_fs_contract.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/runtime/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - added `neuro_unit_port_fs_contract` ztest suite for filesystem ops registration/reset and port path validation
  - extended runtime command capability tests so storage mount/unmount execution is proven through `neuro_unit_port_set_fs_ops()` callbacks
  - updated the canonical unit testing guide with the new port test artifact, case matrix, and coverage estimate
- UT added or updated:
  - added `test_null_fs_ops_reset_to_empty_table`
  - added `test_fs_ops_forward_registered_callbacks`
  - added `test_paths_reject_invalid_values`
  - added `test_storage_mount_requires_port_hook`
  - added `test_storage_commands_use_port_fs_ops`
- Verification evidence:
  - native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`106/106` tests)
  - C style gate after formatting the new port test: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`74` files checked, `0` errors, existing warnings only)
  - app build path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
- Open risks:
  - artifact load/download call paths are indirectly protected through port FS contract and build coverage, but do not yet have fully isolated host-level tests because they still depend on runtime/zenoh integration surfaces
  - network status/probe hooks remain a follow-on test and implementation area
- Rollback notes:
  - rollback can remove the new port test source and the two runtime storage dispatch cases without changing production behavior
- Next action:
  - continue release-1.1.3 by thinning the legacy `storage_ops`/`network_ops` compatibility fields from `app_runtime_cmd_config`, or by adding network status/probe op tests before implementation

2026-04-25: Continued release-1.1.3 implementation with `EXEC-111`, migrating direct artifact filesystem consumers onto the port filesystem contract. Runtime LLEXT artifact loading, zenoh artifact download writes, and update artifact availability checks now consume `neuro_unit_port_get_fs_ops()` rather than calling Zephyr `fs_*` APIs directly; recovery seed storage remains on its existing fs-ops injection seam for testability. — Copilot

#### EXEC-111 Release-1.1.3 Port Filesystem Caller Migration for Artifact Paths

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime.c`
  - `applocation/NeuroLink/neuro_unit/src/zenoh/neuro_unit_zenoh.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_command.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_service.c`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - migrated runtime LLEXT artifact reads in `app_runtime.c` to port filesystem `stat/open/read/close` operations
  - migrated zenoh artifact download writes in `neuro_unit_zenoh.c` to port filesystem `open/write/close` operations
  - migrated update command verify and update service boot-reconcile artifact availability checks to port filesystem `stat`
  - preserved the recovery seed store's dedicated fs-ops injection seam instead of forcing it through the global port contract
- UT added or updated:
  - no new source-level UT cases; existing update/runtime behavior is covered by the native_sim regression and app build in this behavior-preserving migration
- Verification evidence:
  - native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`PROJECT EXECUTION SUCCESSFUL`)
  - app build path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - C style gate: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`73` files checked, `0` errors, existing warnings only)
- Open risks:
  - port filesystem ops still expose Zephyr `fs_file_t`/`fs_dirent` types, so upper modules are decoupled from board wiring but not yet fully opaque from Zephyr FS data structures
  - `neuro_recovery_seed_store.c` intentionally remains on a module-local fs injection seam and still defaults to Zephyr FS calls when not under test
- Rollback notes:
  - rollback can restore the migrated callsites to direct `fs_*` calls without changing protocol payloads or update state transitions
- Next action:
  - continue release-1.1.3 by either adding focused port FS unit tests for default unsupported behavior and artifact call paths, or by thinning the remaining legacy `storage_ops`/`network_ops` compatibility structs from `app_runtime_cmd_config`

2026-04-25: Continued release-1.1.3 implementation with `EXEC-110`, migrating runtime storage/network command dispatch onto the port filesystem/network operation contracts. `app_runtime_cmd` now uses `neuro_unit_port_get_fs_ops()` and `neuro_unit_port_get_network_ops()` for mount/unmount/connect/disconnect while retaining legacy config fields only for source compatibility; DNESP32S3B board SD/Wi-Fi functions now publish direct port ops. A pre-existing zenoh-pico Zephyr source-list issue surfaced during app validation and was fixed by including `src/runtime/*.c` so `_z_executor_spawn` links correctly. — Copilot

#### EXEC-110 Release-1.1.3 Port Caller Migration for Runtime Storage/Network Commands

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic_dnesp32s3b.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/runtime/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `modules/lib/zenoh-pico/zephyr/CMakeLists.txt`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - migrated `APP_RT_CMD_STORAGE_MOUNT`, `APP_RT_CMD_STORAGE_UNMOUNT`, `APP_RT_CMD_NETWORK_CONNECT`, and `APP_RT_CMD_NETWORK_DISCONNECT` execution from legacy `app_runtime_cmd_config` hook tables to port filesystem/network ops
  - kept `app_runtime_cmd_config` support bits as the command capability gate and retained legacy hook structs in the header only for source/config compatibility during the transition
  - added generic weak board-op providers and changed DNESP32S3B wiring so SD/FATFS and Wi-Fi callbacks are published directly as `neuro_unit_port_fs_ops` and `neuro_unit_port_network_ops`
  - updated runtime command capability tests so network execution is proven through `neuro_unit_port_set_network_ops()` rather than direct config hooks
  - fixed the existing zenoh-pico Zephyr module source list by adding `../src/runtime/*.c`, resolving `_z_executor_spawn` link failures exposed during app validation
- UT added or updated:
  - updated `test_app_runtime_cmd_capability.c` to cover port-network-op dispatch and missing-hook behavior through the port contract
- Verification evidence:
  - native_sim Unit regression before app build follow-up: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
  - first app build exposed zenoh-pico `_z_executor_spawn` undefined references; fixed by linking zenoh-pico `src/runtime/*.c`
  - app build after zenoh-pico CMake fix: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - C style gate after formatting: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`73` files checked, `0` errors, existing warnings only)
  - post-format app build: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - post-format native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`35/35` tests)
- Open risks:
  - legacy `storage_ops`/`network_ops` structs remain in `app_runtime_cmd_config` for compatibility and should be removed in a later cleanup once no tests/docs/operators depend on them
  - port network status/probe hooks are still not filled by DNESP32S3B, so richer network introspection remains a follow-on task
  - format script target handling appends to default targets, so `--fix` still normalizes all default C/H files unless the script is enhanced
- Rollback notes:
  - rollback can restore runtime command dispatch to legacy config hooks and remove DNESP32S3B direct port ops, but should keep the zenoh-pico runtime source-list fix if app builds still require it
- Next action:
  - continue release-1.1.3 by migrating direct filesystem consumers such as artifact loading/downloading toward port filesystem helpers, then thin the remaining runtime command compatibility surface

2026-04-25: Continued release-1.1.3 implementation with `EXEC-109`, extracting zenoh transport/session ownership from `neuro_unit.c` into a dedicated zenoh module and helper header. The main Unit file now delegates endpoint override, query reply/publish, query payload helpers, queryable declaration, TCP probe, fetch/download helpers, and the connect monitor loop through `neuro_unit_zenoh`. Main app build passed after cleanup with the migration-introduced unused-function warnings removed. — Copilot

#### EXEC-109 Release-1.1.3 Zenoh Transport Helper/Module Extraction

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_zenoh.h` (new)
  - `applocation/NeuroLink/neuro_unit/src/zenoh/neuro_unit_zenoh.c` (new)
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - introduced `neuro_unit_zenoh` as the transport owner for zenoh endpoint override, session/queryable lifecycle, TCP endpoint probing, query reply helpers, event publish bridge, fetch/download helpers, and the connection monitor thread body
  - kept `neuro_unit.c` responsible for business dispatch, lease/update/app orchestration, and event payload construction while delegating transport operations through a helper API
  - preserved existing queryable key expressions, command/query/update handlers, zenoh connect defaults, retry/log intervals, TCP probe behavior, event publish path, and public shell-facing endpoint override functions
  - removed migration-exposed dead code from `neuro_unit.c` after fetch/download helper ownership moved to the zenoh module
- UT added or updated:
  - no new source-level UT cases; this slice is a structure-preserving extraction of the existing transport implementation
- Verification evidence:
  - app build path after extraction: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - app build path after cleanup: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS, with the migration-introduced `log_memory_snapshot` and `app_state_to_str` unused warnings gone
  - C style gate after formatting: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`73` files checked, `0` errors, existing warnings only)
  - post-format app build: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - post-format native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`100.00%` across listed suites)
- Open risks:
  - `neuro_unit.c` still owns business query handlers and service singletons; a future slice can introduce handler-specific modules if the orchestration file remains too large
  - fetch/download helpers are now available through the zenoh helper header, but current repository state still has no active prepare/download callsite using them
  - host editor diagnostics may still report Zephyr Kconfig macro noise outside a configured build context; the Zephyr build is the authoritative validation for this C/Kconfig slice
- Rollback notes:
  - rollback can move the helper implementations back into `neuro_unit.c`, remove `src/zenoh/neuro_unit_zenoh.c` from CMake, and delete `include/neuro_unit_zenoh.h` without changing protocol semantics
- Next action:
  - continue release-1.1.3 by reviewing handler/service ownership in `neuro_unit.c` and deciding whether app/query/update handlers should split into focused modules or whether port/network caller migration has higher value next

2026-04-25: Continued release-1.1.3 implementation with `EXEC-108`, extracting the UART shell implementation out of the runtime source tree into a dedicated shell module while preserving command registration, command names, and command behavior. Main app build and native_sim Unit regression both passed after the move. — Copilot

#### EXEC-108 Release-1.1.3 UART Shell Module Extraction

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_shell.c` (moved)
  - `applocation/NeuroLink/neuro_unit/src/shell/neuro_unit_shell.c` (new path)
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - moved Zephyr UART shell command handlers and `SHELL_CMD_REGISTER(app, ...)` from `src/runtime` to `src/shell`, making shell ownership explicit and reducing runtime module responsibility
  - updated the application build source list to compile `src/shell/neuro_unit_shell.c`
  - refreshed the release-1.1.3 hotspot note so the shell follow-on work points at the extracted module path
  - intentionally preserved existing command names, help strings, guard behavior, runtime command dispatch, storage listing behavior, and zenoh endpoint override commands
- UT added or updated:
  - no new source-level UT cases; this slice is a behavior-preserving file/module extraction
- Verification evidence:
  - static editor diagnostics for moved shell source, app CMake, and ledger => no errors
  - app build path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
- Open risks:
  - shell command handlers are now in a dedicated source tree, but command grouping is still monolithic inside one file; future slices can split lifecycle/storage/network/zenoh subcommands if the file continues to grow
  - zenoh shell commands still call `neuro_unit_*_zenoh_connect_*` APIs directly until the zenoh transport layer is extracted
- Rollback notes:
  - rollback can move `src/shell/neuro_unit_shell.c` back to `src/runtime/app_runtime_shell.c` and restore the previous CMake source path without changing command behavior
- Next action:
  - continue release-1.1.3 with `EXEC-109` by extracting zenoh transport/session helpers from `neuro_unit.c` into a dedicated zenoh module and helper header

2026-04-25: Started release-1.1.3 implementation from the post-1.1.2 closure baseline, with focus on code-structure and quality optimization for clearer layer responsibilities and stronger extension points. Created pre-research baseline `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md` and completed `EXEC-107` as the first execution slice. Initial implementation added behavior-preserving port filesystem/network contract scaffolding, registered provider-level ops/path metadata, guarded Zephyr FS adapter calls for no-filesystem test configurations, and moved the shell `ls` directory traversal onto the new port filesystem contract. Focused native_sim Unit validation passed after the contract and shell migration. — Copilot

#### EXEC-107 Release-1.1.3 Kickoff and Port FS/Network Contract Scaffolding

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.3_PRE_RESEARCH.md` (new)
  - `applocation/NeuroLink/neuro_unit/include/port/neuro_unit_port.h`
  - `applocation/NeuroLink/neuro_unit/include/port/neuro_unit_port_fs.h` (new)
  - `applocation/NeuroLink/neuro_unit/include/port/neuro_unit_port_network.h` (new)
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_contract.c` (new)
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_shell.c`
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - formally opened release-1.1.3 pre-research with explicit scope/acceptance/risk baseline and phased execution plan
  - started implementation with behavior-safe contract scaffolding for port-layer filesystem/network responsibilities so upcoming refactors can migrate callsites without changing user-facing behavior first
  - introduced provider-level ops registry and path metadata bridge as a neutral seam between board capability injection and upper modules
  - filled the filesystem contract with Zephyr FS adapter hooks, guarded those hooks behind `CONFIG_FILE_SYSTEM` for no-FS native_sim/unit builds, and moved shell `ls` directory traversal from direct `fs_*` calls to `neuro_unit_port_get_fs_ops()`
- UT added or updated:
  - no new source-level UT cases in this kickoff slice
  - existing native_sim Unit suites remained the behavior guardrail for the no-protocol-change scaffolding
- Verification evidence:
  - static editor diagnostics for touched port/doc/CMake/ledger files => no errors
  - first validation attempt exposed undefined `fs_opendir`/`fs_readdir`/`fs_closedir` links in the no-FS native_sim Unit configuration, confirming the review concern about unconditional Zephyr FS adapter calls
  - after adding `CONFIG_FILE_SYSTEM` guards: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
- Open risks:
  - additional port APIs are introduced before caller migration, so temporary dual-path ownership exists until follow-on slices move runtime/shell/neuro_unit callsites
  - zenoh extraction remains pending; `neuro_unit.c` transport coupling is intentionally unchanged in this kickoff step
- Rollback notes:
  - rollback can remove the new contract files and provider-bridge wiring while keeping release-1.1.2 runtime behavior intact
- Next action:
  - continue release-1.1.3 by extracting UART shell registration/handlers into a dedicated shell module while preserving existing command names and board behavior

2026-04-23: Marked release-1.1.2 as complete after closing the architecture modularization track and the Linux reliability/validation track on the current repository state. Promoted `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` to `RELEASE_TARGET = "1.1.2"`, appended final closure review notes to `applocation/NeuroLink/docs/project/RELEASE_1.1.2_QUALITY_BASELINE.md`, and confirmed the release evidence set already captured in this ledger remains green: `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`7/7`), `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh` => PASS, `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk` => PASS, `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app` => PASS, `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text` => PASS, and `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5` => PASS with latest evidence `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260423-185830.ndjson`. Release-1.1.2 is now closed in this ledger; follow-on work should open a new release or maintenance slice rather than extend this one. — Copilot

#### EXEC-106 Release-1.1.2 Linux Script Reliability Hardening and Full Validation Sweep

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/scripts/build_neurolink.sh`
  - `applocation/NeuroLink/scripts/setup_neurolink_env.sh`
  - `applocation/NeuroLink/scripts/preflight_neurolink_linux.sh`
  - `applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh`
  - `applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh`
  - `applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh`
  - `applocation/NeuroLink/scripts/monitor_neurolink_uart.sh`
  - `applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
  - `applocation/NeuroLink/scripts/format_neurolink_c_style.sh`
  - `applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`
  - `applocation/NeuroLink/tests/scripts/run_all_tests.sh` (new)
  - `applocation/NeuroLink/tests/scripts/test_build_neurolink.sh` (new)
  - `applocation/NeuroLink/tests/scripts/test_style_scripts.sh` (new)
  - `applocation/NeuroLink/tests/scripts/test_setup_neurolink_env.sh` (new)
  - `applocation/NeuroLink/tests/scripts/test_preflight_neurolink_linux.sh` (new)
  - `applocation/NeuroLink/tests/scripts/test_linux_scripts_help.sh` (new)
  - `applocation/NeuroLink/tests/scripts/test_run_zenoh_router_wsl.sh` (new)
  - `applocation/NeuroLink/tests/scripts/test_install_zenoh_router_wsl.sh` (new)
  - `.github/workflows/neurolink_unit_ut_linux.yml`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - hardened the Linux-facing operator/build scripts so they are directly runnable and safer under real host conditions instead of depending on implicit shell state
  - fixed build-script validation ordering and CMake cache parsing, improved setup strict-mode behavior when multiple Zephyr SDK installations are present, and made style scripts self-bootstrap the project environment before requiring `clang-format`/`perl`
  - improved preflight/router reliability with router-helper injection, startup readiness polling, and explicit `router_failed_to_start` classification when background launch succeeds superficially but the TCP port never becomes ready
  - improved WSL board-prep and router helpers by adding attach rollback for usbipd failures, PID persistence/early-exit detection for background `zenohd`, safer standalone zip extraction guards, and clearer UART/style/build failure reporting
  - added a dedicated Linux shell regression suite covering build validation, style-script direct invocation, setup strict-mode SDK handling, preflight failure paths, safe help entrypoints, router background PID handling, and installer archive-safety checks; wired the suite into the Linux CI workflow
- UT added or updated:
  - added shell regression coverage under `applocation/NeuroLink/tests/scripts/` for:
    - build script validation and CMake cache parsing
    - direct style/check script execution
    - setup strict-mode multi-SDK detection
    - preflight router-start failure classification
    - help/safe preview entrypoints across Linux shell scripts
    - router helper background PID file behavior
    - installer archive traversal rejection
- Verification evidence:
  - shell regression suite: `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`7/7 tests passed`)
  - Linux UT/VM path: `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh` => PASS (`twister_native_sim_rc=0`, `qemu_status=passed`)
  - default Linux build path with style gate: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk` => PASS
  - default Linux external-app path with style gate: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app` => PASS
  - real-device readiness gate: `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text` => PASS (`status=ready`, `/dev/ttyACM0` present)
  - real-device end-to-end smoke: `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5` => PASS
  - smoke evidence artifact: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260423-185830.ndjson`
- Open risks:
  - direct shell-script regression now covers entrypoints and key failure modes, but some WSL-host interactions still depend on external tools (`usbipd.exe`, `sudo`, package mirrors) that are best validated periodically on the target operator machine
  - style tooling still reports non-blocking warning backlog classes (for example `EXPORT_SYMBOL` placement and `ENOSYS` usage) outside this reliability slice
- Rollback notes:
  - rollback can remove the new shell regression suite and restore prior script behavior without affecting protocol/runtime implementation, but Linux operator diagnostics and CI coverage would become weaker again
- Next action:
  - continue by shrinking remaining warning backlog and optionally adding scripted negative-path smoke fixtures for router-down / serial-missing / no-reply classifications in CI-safe mock mode

#### EXEC-105 Release-1.1.2 neuro_unit Update Application Service Layer and Unified Transaction Context

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_update_service.h` (new)
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_service.c` (new)
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_update_command.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_command.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_dispatch.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_request_policy.c`
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_service.c` (new)
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_command.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_dispatch.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/request/test_neuro_request_policy.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - entered release-1.1.2 step-4 by sinking update command business transaction orchestration from `neuro_unit.c` into a dedicated application service layer (`neuro_unit_update_service`)
  - moved recovery-seed lifecycle coordination (init/load/apply/reconcile/persist) into the service and reduced `neuro_unit.c` to thin adapters for dispatch ingress and event/runtime wiring
  - upgraded update-command callback contract to context-aware callbacks (`user_ctx`) and added a unified transaction logging hook so `prepare/verify/activate/recover` share consistent action/request/phase context
  - added `recover` alias compatibility while preserving `rollback` behavior, and wired policy+dispatch lifecycle gate to accept both routes
  - kept service boundaries explicit: dispatch handles route/policy gating, update service owns transaction orchestration, update command owns action execution details
- UT added or updated:
  - added `test_neuro_unit_update_service.c` coverage for:
    - service prepare delegation + success reply
    - recover alias preservation in transaction context
    - recovery seed gate failure propagation when storage is not ready
  - extended `test_neuro_unit_update_command.c` coverage for:
    - transaction log callback contract on prepare
    - recover alias routing into rollback handler semantics
  - extended `test_neuro_unit_dispatch.c` coverage for:
    - recover route lifecycle gate + dispatch
  - extended `test_neuro_request_policy.c` coverage for:
    - recover action metadata policy mapping
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -t run` => PASS (`neuro_unit_update_service`, `neuro_unit_dispatch`, `neuro_unit_update_command` suites all passed, including recover-alias cases)
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS
- Open risks:
  - transaction context is now unified for update flows, but command/app cross-domain orchestration still spans multiple modules and can be further collapsed into narrower service contracts in the next slice
  - event payload strings remain hand-assembled JSON; future schema expansion should keep response/event builders centralized and UT assertions synchronized
- Rollback notes:
  - rollback can remove `neuro_unit_update_service` and restore direct `neuro_unit.c -> neuro_unit_update_command` wiring while retaining protocol routes and callback contracts
- Next action:
  - continue release-1.1.2 architecture track by extracting app-command transaction orchestration into parallel service boundaries and aligning transaction/event correlation IDs across command/query/update planes

#### EXEC-104 Release-1.1.2 neuro_unit Response/Helper Sink and Orchestration Thinning

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_response.h` (new)
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_response.c` (new)
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_response.c` (new)
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - completed the third architecture slice by sinking remaining response JSON assembly and shared metadata parsing/validation helpers from `neuro_unit.c` into a dedicated response/helper module (`neuro_unit_response`)
  - reduced composition-root complexity in `neuro_unit.c` by replacing inline builders for lease/query/error replies with focused module calls and uniform failure handling (`reply build failed` paths)
  - centralized response contracts for error, lease acquire/release, query device, query apps, and query leases payloads so protocol-shape ownership is explicit and reusable
  - removed local response formatting helpers from orchestration (`json_append`, local runtime/artifact string mappers, local request metadata parse helper)
  - hardened unit-test portability by keeping network-state string mapping local to the response module instead of introducing a new link dependency on network-manager internals
- UT added or updated:
  - added `test_neuro_unit_response.c` coverage for:
    - error response contract fields
    - lease acquire/release response contracts
    - query device/apps/leases response contracts
    - request metadata payload validation success/failure (including target-node mismatch)
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -t run` => PASS (`SUITE PASS - [neuro_unit_response]: pass=6 fail=0`)
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS
- Open risks:
  - response assembly is now modularized, but core command business flow in `neuro_unit.c` still contains non-trivial state orchestration and can be further decomposed in the next slice
  - payload builders remain string-based; any future response schema growth should keep UT assertions aligned with added fields and overflow safeguards
- Rollback notes:
  - rollback can inline response helper calls back into `neuro_unit.c` and remove `neuro_unit_response` without changing external route contracts
- Next action:
  - continue release-1.1.2 decoupling by extracting command business transactions from `neuro_unit.c` into focused application-service modules while keeping dispatch/response layers as stable boundaries

#### EXEC-103 Release-1.1.2 neuro_unit Routing Dispatch Layer Extraction

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_dispatch.h` (new)
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_dispatch.c` (new)
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_dispatch.c` (new)
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - continued release-1.1.2 framework decoupling by extracting command/query/update route branching out of `neuro_unit.c` into a dedicated dispatch layer (`neuro_unit_dispatch`)
  - introduced an explicit dispatch-ops contract so routing logic depends on callback interfaces instead of direct static-global orchestration internals
  - reduced `neuro_unit.c` query handlers to thin ingress adapters (`key/payload/metadata` extraction plus delegation), preserving protocol behavior while lowering branch density in the composition root
  - centralized route parsing and admission gates in the new module: transport-health gating, metadata requirement checks, app-route extraction, lifecycle update recovery-seed gate, and unsupported-path mapping
  - added focused UT for dispatch routing semantics and guardrail behavior (transport gate, lifecycle gate, route extraction)
- UT added or updated:
  - added `test_neuro_unit_dispatch.c` coverage for:
    - command lease acquire dispatch
    - command app route extraction (`app_id`, `action`)
    - update lifecycle recovery gate pass/fail behavior
    - query transport-unhealthy 503 behavior
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS
- Open risks:
  - dispatch extraction is currently route-level and callback-driven; deeper command payload/business orchestration in `neuro_unit.c` remains for the next architecture slice
  - full dispatch contract hardening against future route expansion still depends on keeping route-policy and dispatch tests updated together
- Rollback notes:
  - rollback can inline dispatch calls back into `neuro_unit.c` handlers and remove the dispatch module without changing external protocol contracts
- Next action:
  - continue release-1.1.2 decoupling by extracting shared command/query payload assembly and response-building helpers from `neuro_unit.c` into framework-owned modules that consume the dispatch contract

#### EXEC-102 Release-1.1.2 Unit Diagnostics Architecture Foundation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/Kconfig`
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_diag.h` (new)
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_diag.c` (new)
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_event.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_state_registry.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_state_registry.c` (new)
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - started release-1.1.2 framework decoupling from an architecture boundary rather than a localized patch by adding a dedicated Unit diagnostics layer (`neuro_unit_diag`) for correlation context formatting, contract-error signaling, event publish tracing, and state transition logs
  - introduced Unit-level compile-time debug policy in `Kconfig` (`NEUROLINK_UNIT_DEBUG_MODE`, `NEUROLINK_UNIT_DEBUG_VERBOSE_EVENTS`, `NEUROLINK_UNIT_DEBUG_VERBOSE_STATE`) so framework diagnostics are controlled independently from low-level zenoh-pico transport debug
  - rewired `neuro_unit_event.c` to route validation and publish-path observability through diagnostics APIs, ensuring publish attempts and terminal publish outcomes are explicitly logged as framework events
  - upgraded `neuro_state_registry.c` from silent mutation to semantic transition logging with old/new values and version correlation, including verbose snapshot emission behind debug switches
  - added state-registry UT coverage on the canonical `tests/unit` path to lock the semantic-version contract and snapshot updates while preserving behavior compatibility
- UT added or updated:
  - added `test_neuro_state_registry.c` with coverage for:
    - session-ready semantic version bump rules
    - network to health snapshot propagation and no-op update stability
    - runtime/lease/update semantic transition version behavior
- Verification evidence:
  - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`13 test suites`, `183 tests passed`, `0 failed`)
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
  - `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS
- Open risks:
  - this slice establishes diagnostics architecture and event/state observability, but the main orchestration hotspot in `neuro_unit.c` is not decomposed yet and remains the next coupling target
  - existing non-slice warning backlog (for example legacy `strnlen` warning contexts) remains outside this change scope and should be handled in a focused cleanup slice
- Rollback notes:
  - rollback can remove the diagnostics module and restore direct event/state logging-free paths without protocol surface changes; event payload contracts and app-facing APIs remain unchanged
- Next action:
  - continue release-1.1.2 architecture track by extracting shared dispatch and diagnostics hooks from `neuro_unit.c` into dedicated framework-owned routing modules while extending UT around route/diagnostic contracts

#### EXEC-101 Release-1.1.2 Automated Real-Device Smoke Recovery and Validation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - resumed the blocked real-device validation path after the earlier `no_reply_board_not_attached` state and verified that the remaining issue was environmental board attachment rather than a new runtime regression in the EDK external-app pipeline
  - used the existing automated board-prepare flow to attach the CH343 device into WSL, capture UART-driven bring-up, run preflight, and confirm `query device` returned the expected board identity `dnesp32s3b` for node `unit-01`
  - reran the canonical Linux automated smoke script end-to-end and confirmed the external-app deployment path (`prepare -> verify -> activate -> monitor events`) now passes on real hardware with the aligned `unit-app` artifact flow
- UT added or updated:
  - no new source-level UT cases in this slice
  - validation focus was automated real-device smoke execution using the existing Linux operator scripts
- Verification evidence:
  - automated board preparation: `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --wifi-ssid cemetery --wifi-credential goodluck1024 --capture-duration-sec 30` => PASS (usbipd attach succeeded, `/dev/ttyACM0` detected, preflight ready, `query device` returned `board=dnesp32s3b`)
  - automated real-device smoke: `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5` => PASS
  - smoke summary artifact: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260423-174549.summary.txt` => `result=PASS`
  - smoke evidence artifact: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260423-174549.ndjson`
- Open risks:
  - real-device automation is currently healthy in this session, but future runs still depend on WSL USB attachment state and router availability before the scripts can reach Unit query/update paths
  - PowerShell-side runtime validation remains pending on a host with `pwsh` available
- Rollback notes:
  - evidence-only slice; no production code changes were required to restore the automated real-device path in this run
- Next action:
  - continue release-1.1.2 framework decoupling on top of the restored real-device automation baseline, and preserve this smoke path as the first regression check after future host/app-boundary changes

#### EXEC-100 Release-1.1.2 App Helper Surface + Linux Smoke Path Alignment and Style-Gate Repair

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_app_api.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_event.c`
  - `applocation/NeuroLink/subprojects/neuro_unit_app/src/main.c`
  - `applocation/NeuroLink/scripts/preflight_neurolink_linux.sh`
  - `applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`
  - `applocation/NeuroLink/scripts/format_neurolink_c_style.sh`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_neuro_unit_app_api.c`
  - `applocation/NeuroLink/neuro_unit/include/*.h` (style normalization sweep)
  - `applocation/NeuroLink/neuro_unit/src/*.c` (style normalization sweep)
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/**/*.c` (style normalization sweep)
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - promoted app-side callback payload and command reply JSON construction into framework-owned helper APIs (`neuro_unit_publish_callback_event`, `neuro_unit_write_command_reply_json`) exposed through `neuro_unit_app_api.h`, and switched the standalone LLEXT sample app to consume those helpers instead of hand-building JSON
  - aligned Linux preflight/smoke scripts with the explicit EDK external-app path by wiring missing-artifact remediation to `build_neurolink.sh --preset unit-app --no-c-style-check` and updating operator guidance away from internal-target assumptions
  - fixed style tooling root cause for subproject files by forcing `format_neurolink_c_style.sh` to use the canonical project style file explicitly (`-style=file:${STYLE_FILE}`), then repaired style drift with a targeted normalization sweep
- UT added or updated:
  - extended `test_neuro_unit_app_api.c` coverage to include framework helper serialization/publish contract checks for callback payload and command reply JSON
  - existing Unit suites rerun on `native_sim` after style/tooling fixes
- Verification evidence:
  - external app build through EDK path: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS
  - Unit UT regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (all tests passed)
  - Linux style gate after script/tooling fix and normalization sweep: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh --target applocation/NeuroLink/subprojects/neuro_unit_app/src` => PASS (`errors=0`, warnings remain)
  - end-to-end script attempts now run through the aligned path, but runtime environment remained offline for device query (`no_reply`) in current host state
- Open risks:
  - smoke/preflight script pathing is aligned, but real-board e2e closure still depends on live board/router reachability in the current lab session; latest runs still reported `query_device -> no_reply`
  - style gate currently passes with warnings; if warning-free baseline is required, remaining warning classes (for example `ENOSYS` semantics and grouped `EXPORT_SYMBOL` placement) need a dedicated cleanup slice
  - PowerShell runtime validation remains pending on a host with `pwsh` available
- Rollback notes:
  - rollback can revert helper APIs and return app-local JSON assembly while preserving the standalone app extraction boundary
  - script rollback can revert preflight/smoke artifact remediation back to manual pre-build behavior if operator policy prefers explicit build-only workflows
- Next action:
  - continue release-1.1.2 framework decoupling by expanding app-facing helper contracts where value is clear, and close the remaining smoke `no_reply` operational gap with live board/router diagnostics evidence

#### EXEC-099 Release-1.1.2 Standalone LLEXT App Extraction and EDK Build Path

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_neuro_unit_app_api.c`
  - `applocation/NeuroLink/subprojects/neuro_unit_app/CMakeLists.txt`
  - `applocation/NeuroLink/subprojects/neuro_unit_app/toolchain.cmake`
  - `applocation/NeuroLink/subprojects/neuro_unit_app/src/main.c`
  - `applocation/NeuroLink/scripts/build_neurolink.sh`
  - `applocation/NeuroLink/scripts/build_neurolink.ps1`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - extracted the callback-smoke sample LLEXT app out of the main `neuro_unit` build into a dedicated external subproject under `applocation/NeuroLink/subprojects/neuro_unit_app`, preserving the same lifecycle symbols, manifest contract, and callback-smoke behavior while removing the in-tree `add_llext_target()` ownership from `neuro_unit/CMakeLists.txt`
  - converted the Linux and PowerShell build wrappers so `unit-edk`, `unit-app`, and the compatibility alias `unit-ext` now build the Unit host, generate and extract `llext-edk`, compile the standalone app against that EDK, and restage the resulting artifact back to `build/neurolink_unit/llext/neuro_unit_app.llext` for existing smoke and CLI consumers
  - promoted the public app-facing include roots into the generated EDK and added a focused Unit regression test that exercises the stable external-app contract through `neuro_unit_app_api.h` plus `app_runtime_manifest.h`, instead of only relying on internal framework headers in tests
- UT added or updated:
  - added `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_neuro_unit_app_api.c`
  - updated `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt` to compile the new public-ABI regression
- Verification evidence:
  - focused standalone app build through the new EDK pipeline: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ext --no-c-style-check` => PASS (`Built target neuro_unit_app`)
  - focused default-preset wrapper check for the new external app flow: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS (`Built target neuro_unit_app`)
  - focused Unit regression after adding public-ABI coverage: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (all test suites passed)
- Open risks:
  - PowerShell wrapper validation could not be executed in the current Linux environment because `pwsh` is not installed, so that script slice is code-reviewed and syntax-shaped but not runtime-verified here
  - the host build still emits unrelated pre-existing zenoh-pico macro redefinition warnings and a pre-existing `strnlen` implicit-declaration warning in the native_sim Unit test build; these were not introduced by this slice and were left untouched
  - existing smoke/preflight scripts continue to rely on the stable staged artifact path; this slice preserves that path intentionally, but any future relocation must update those consumers together
- Rollback notes:
  - rollback can restore the prior in-tree LLEXT target in `neuro_unit/CMakeLists.txt`, remove the standalone app subproject, and point `unit-ext` back to the internal target without changing Unit protocol behavior
- Next action:
  - continue the release-1.1.2 framework-decoupling track by splitting more internal `neuro_unit` orchestration into clearer framework vs app-facing surfaces, while extending smoke automation to exercise the EDK-produced standalone app path explicitly

#### EXEC-098 Release-1.1.2 Unit App-Facing ABI Split Kickoff

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_app_api.h`
  - `applocation/NeuroLink/neuro_unit/include/neuro_request_envelope.h`
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit_event.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - started the release-1.1.2 Unit-side framework decoupling track from the smallest behavior-safe boundary: the current sample LLEXT app no longer includes `neuro_request_envelope.h` and `neuro_unit_event.h` directly as internal framework headers
  - added a dedicated minimal app-facing header, `neuro_unit_app_api.h`, that exposes only the currently intentional LLEXT app contract (`neuro_unit_publish_app_event()` plus the lightweight JSON extraction helpers already exported by the runtime)
  - rewired `neuro_unit_app_llext.c` to consume the new app-facing API surface and normalized the touched files to the repository Linux-style baseline without changing callback-smoke behavior, symbol exports, or the existing in-tree LLEXT build contract
- UT added or updated:
  - no new source-level tests in this slice
  - existing Unit module tests remained the guardrail for the shared-header change
- Verification evidence:
  - focused LLEXT build validation after the app-facing header split: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ext --no-c-style-check` => PASS (`ninja: no work to do`)
  - focused Unit regression after the shared-header change: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`PROJECT EXECUTION SUCCESSFUL`)
- Open risks:
  - this slice separates the first app-facing ABI surface, but the sample callback app is still built inside `neuro_unit/CMakeLists.txt`; external project extraction and EDK-driven standalone build remain open
  - `neuro_unit_app_api.h` currently lives beside internal headers in the same include root; a later slice should move toward a clearer public-vs-internal header layout once the external app project exists
  - the canonical build wrapper still runs a broad repository style gate before build; that gate can mask narrow compile validation unless the touched files are already clean
- Rollback notes:
  - rollback can restore the previous direct includes in `neuro_unit_app_llext.c` and remove `neuro_unit_app_api.h` without changing runtime protocol behavior or test expectations
- Next action:
  - continue release-1.1.2 framework decoupling by extracting the standalone callback-smoke LLEXT app into its own project and making `neuro_unit` produce the EDK/public app ABI as the host-side build boundary

#### EXEC-097 Release-1.1.2 CLI Parser Registration Decomposition

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - continued the low-risk CLI quality track by decomposing the largest single function in `core_cli.py`, `build_parser()`, into smaller registration helpers grouped by concern instead of leaving all argument and command-family wiring in one monolithic block
  - extracted shared top-level parser argument registration into `add_common_parser_arguments()` and split command registration into `add_legacy_commands()` plus `add_grouped_alias_commands()` while preserving command names, argument contracts, and handler wiring
  - kept this slice intentionally structural only so complexity drops without mixing in protocol or output-shape changes
- UT added or updated:
  - no new source-level tests in this slice
  - existing CLI parser and command-path tests remained the behavioral guardrail
- Verification evidence:
  - focused CLI regression after parser decomposition: `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py -q` => PASS (`24 passed`)
- Open risks:
  - `handle_app_callback_smoke()` still contains the densest remaining orchestration logic in `core_cli.py`
  - `argparse._SubParsersAction` is used only for type annotation convenience in helpers; if a stricter typing policy is adopted later, the annotation may need to be relaxed to avoid private-API references in type hints
- Rollback notes:
  - rollback can inline the helper bodies back into `build_parser()` without affecting any runtime protocol behavior
- Next action:
  - continue with callback-smoke step-runner extraction in `core_cli.py`, or shift to the first Unit-side framework boundary cleanup once the CLI orchestration hotspot is reduced further

#### EXEC-095 Release-1.1.2 Callback Smoke Result Envelope Normalization

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`
  - `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - continued the release-1.1.2 CLI quality track by normalizing the `app-callback-smoke` result envelope instead of leaving failure branches to print partial results before final cleanup completed
  - added a direct regression test for the callback-smoke query-failure path, which exposed that the previous implementation printed JSON before the `finally` block appended the `lease_release` step
  - refactored `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` so callback-smoke result construction is centralized in dedicated helpers and emitted only once after cleanup, making failure and success paths use the same output contract
- UT added or updated:
  - added `test_handle_app_callback_smoke_returns_failed_result_on_query_error` in `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`
- Verification evidence:
  - focused CLI regression after adding the failing-path test initially exposed the envelope-order defect (`steps[1]` missing because `lease_release` was appended after JSON output)
  - focused CLI regression after normalization fix: `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py -q` => PASS (`24 passed`)
- Open risks:
  - `handle_app_callback_smoke()` still contains orchestration-heavy control flow and remains a candidate for step-runner extraction in a later slice
  - parser construction in `build_parser()` remains the largest single complexity hotspot in `core_cli.py`
- Rollback notes:
  - rollback can restore inline result assembly in `handle_app_callback_smoke()`, but doing so would reintroduce the inconsistent failure output ordering now covered by regression
- Next action:
  - either split parser registration by command family for the next low-risk complexity reduction, or continue extracting the callback-smoke step runner now that the result contract is centralized

#### EXEC-093 Release-1.1.2 CLI Listener Lifecycle Extraction with Regression-First Tests

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`
  - `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - started the first behavior-preserving refactor slice selected by the release-1.1.2 quality baseline and kept scope strictly on the Unit CLI listener lifecycle surface
  - added regression-first tests for listener edge behavior so the refactor is protected by explicit coverage for `plain_subscriber` fallback and `KeyboardInterrupt` cleanup semantics
  - extracted `subscribe_to_events()` into smaller behavior-focused helpers for collection and result emission, reducing local coupling between subscriber setup, ready-file handling, event collection strategy, and final JSON output without changing the public command contract
- UT added or updated:
  - added listener fallback coverage for `plain_subscriber` result mode in `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`
  - added cleanup coverage ensuring subscriber `undeclare()` still runs on `KeyboardInterrupt` in `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`
- Verification evidence:
  - focused CLI regression after test landing: `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py -q` => PASS (`23 passed`)
  - focused CLI regression after listener lifecycle refactor: `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py -q` => PASS (`23 passed`)
- Open risks:
  - `handle_app_callback_smoke()` remains a longer orchestration path and is still a likely follow-on target for result-envelope normalization and step-runner extraction
  - `build_parser()` remains the largest single function in `core_cli.py`; it was intentionally deferred to keep this slice narrow and behavior-safe
- Rollback notes:
  - rollback can restore the pre-extraction `subscribe_to_events()` inline flow while retaining the new tests as contract guards for the next attempt
- Next action:
  - continue with diagnostics normalization inside the CLI event/smoke paths, or open the next quality slice to split parser registration by command family while preserving argument compatibility

#### EXEC-092 Release-1.1.2 Quality Baseline Capture and Refactor Entry Selection

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.2_PRE_RESEARCH.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.2_QUALITY_BASELINE.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - started actual release-1.1.2 execution by converting the pre-research track from callback-only reliability planning into a dual-track baseline covering code quality uplift and framework optimization
  - captured the first repository-grounded quality baseline for the active hot-path files and identified concrete first refactor candidates instead of leaving the new quality goals at narrative level only
  - confirmed the highest-value initial entry point is the Unit CLI listener lifecycle surface (`subscribe_to_events`, adjacent subscriber helpers, and the larger `handle_app_callback_smoke` orchestration path), while `neuro_unit.c` connection and artifact paths remain the next heavier framework-side extraction candidates
- UT added or updated:
  - no source-level UT changes in this baseline-capture slice
  - existing CLI and Unit runnable checks remain the locked safety net for subsequent refactor slices
- Verification evidence:
  - quality baseline report created: `applocation/NeuroLink/docs/project/RELEASE_1.1.2_QUALITY_BASELINE.md`
  - baseline findings captured from current source state:
    - `core_cli.py` top size hotspots include `build_parser()` (~281 lines), `handle_app_callback_smoke()` (~160 lines), and `collect_subscriber_events_threaded()` (~93 lines)
    - `neuro_unit.c` top size hotspots include `neuro_unit_connect_once()` (~89 lines), `neuro_download_artifact()` (~83 lines), and `neuro_unit_connect_thread()` (~78 lines)
    - `neuro_unit.c` current coupling snapshot includes `34` include lines and `16` project-local headers
    - `core_cli.py` JSON-capable output footprint currently includes `28` `print_json`/`json.dumps` call sites
  - executable guardrails already available and still green on current workspace baseline:
    - `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py -q` => PASS (`21 passed`)
    - `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS (`11 suites`, `77 tests`)
- Open risks:
  - the current baseline uses lightweight line-count and dependency-inventory heuristics rather than a dedicated static-analysis stack, so later slices may want stricter metrics tooling if the repository adopts one
  - `neuro_unit.c` remains a high-coupling integration file; framework-side refactor should proceed only after the lower-risk CLI listener slice lands with tests first
- Rollback notes:
  - this slice is documentation and execution-baseline capture only; rollback can remove the new quality baseline document and ledger entry without affecting runtime behavior
- Next action:
  - start `EXEC-093` by adding or tightening listener negative-path tests, then extract CLI listener lifecycle helpers with behavior-preserving refactor and rerun the locked CLI + Unit validations

2026-04-23: Completed a code-grounded closure audit for release-1.1.1 and started release-1.1.2 pre-research. Rechecked implementation anchors against live source: `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` still targets `RELEASE_TARGET = "1.1.1"` and contains `app-callback-config`, `app-events`, grouped alias paths, listener-mode diagnostics, and `fifo_channel` strategy fallback; Unit runtime confirms `network_disconnect` end-to-end plus framework-owned app event publishing through `applocation/NeuroLink/neuro_unit/src/neuro_unit_event.c` and callback emission in `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c`. Re-ran focused executable checks in this workspace: `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py -q` => `21 passed`; `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => `11 suites`, `77 tests` all PASS. Audit conclusion: release-1.1.1 code and local runnable verification remain consistent with closure claims; remaining caution is evidence traceability because `applocation/NeuroLink/smoke-evidence/` is currently empty after the closeout cleanup step. Started release-1.1.2 pre-research baseline at `applocation/NeuroLink/docs/project/RELEASE_1.1.2_PRE_RESEARCH.md` with scope, risk-driven workstreams, acceptance criteria, and immediate next actions focused on standalone listener reliability and evidence governance. — Copilot

2026-04-23: Marked release-1.1.1 as complete after final standalone callback listener validation and repository hygiene cleanup. Final callback replay on `unit-01` now consistently captures app events in separate listener mode (`events_count=3`, `listener_mode=fifo_channel`) using the corrected lease/control sequence, confirming item-2 closure beyond same-session smoke. Per release closeout cleanup request, removed generated build/test artifacts at workspace root (`build/`, `out-test/`, `twister-out*`, `.pytest_cache/`), cleared all generated evidence under `applocation/NeuroLink/smoke-evidence/`, and deleted obsolete root helper `run_validation.sh` (no project references and stale command contract against current `core_cli.py`). This leaves only source/config/tooling trees in the root workspace and preserves release closure status in this ledger. — Copilot

2026-04-22: Closed the outstanding standalone listener gap for release-1.1.1 item 2 after enabling end-to-end debug and fixing host-side robustness semantics. With router debug enabled and board rebuilt/flashed on the new zenoh-pico debug profile, replayed the two-terminal standalone listener flow using corrected lease/control ordering and the hardened `core_cli.py` retry/result rules. Latest replay now captures callback events in separate-process mode: `applocation/NeuroLink/smoke-evidence/callback-listener/standalone_events.json` reports `events_count=3` with `listener_mode=fifo_channel` after `lease acquire -> app-callback-config -> app-invoke x2 -> lease release`. This closes the prior `events: []` signature under real-board standalone listener validation and confirms item-2 behavior is now stable with explicit diagnostics (`attempt/max_attempts/retried`, listener strategy output, router debug controls) for future enhancements. — Copilot

2026-04-22: Landed a robustness-focused callback-listener hardening slice instead of another minimal workaround. Added explicit zenoh router debug controls (`--debug`, `--rust-log`) in `applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh` and propagated them through Linux operator entrypoints (`applocation/NeuroLink/scripts/preflight_neurolink_linux.sh`, `applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh`, `applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`) so router debug can be enabled consistently from preflight/prepare/smoke flows. Enabled configurable zenoh-pico debug mode on Unit side by introducing `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG` and `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL` in `applocation/NeuroLink/neuro_unit/Kconfig`, wiring compile definitions in `applocation/NeuroLink/neuro_unit/CMakeLists.txt`, and setting the active board profile `applocation/NeuroLink/neuro_unit/boards/dnesp32s3b_esp32s3_procpu.conf` to debug level 3. Refactored `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` for maintainability and resilience: added structured retry policies (session open + transient query retries with backoff), resilient session open path, explicit subscriber strategy declaration (`fifo_channel` / callback / plain), listener-mode diagnostics in JSON output, and configurable keepalive pump interval for event listeners. Extended CLI regression coverage in `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` with retry/session-open tests; focused suite is now `19 passed`. Validation on this workspace: Python syntax checks pass, shell syntax checks pass for modified scripts, Unit build passes with new debug Kconfig options accepted, and router debug launch now reports `router_rust_log=debug` with evidence under `applocation/NeuroLink/smoke-evidence/zenoh-router/20260422T155046Z/zenohd.log`. — Copilot

2026-04-22: Pushed the standalone `app-events` listener investigation to a tighter closure point and confirmed the remaining gap is deeper than simple host callback timing. Continued iterating only inside `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`: after the earlier ready-file ordering fix, additionally retained a strong reference to the subscription callback, forced explicit `zenoh.handlers.Callback(..., indirect=False)` when available, added a lightweight same-session query pump during the callback wait window, and finally switched standalone subscriptions to prefer an explicit `zenoh.handlers.FifoChannel(64)` when the binding exposes channel handlers. Focused Python regression remains green at `17 passed`. Despite those host-side changes, repeated real-board two-terminal replays on `unit-01` still end in the same signature: control-plane operations succeed end-to-end with fixed explicit lease ids, invoke replies report `publish_ret: 0`, and the app-side callback path continues to return `status: ok`, but the separate listener process still writes `{"ok": true, "subscription": "neuro/unit-01/event/app/neuro_unit_app/**", "events": []}` to `applocation/NeuroLink/smoke-evidence/callback-listener/standalone_events.json`. Latest successful control evidence is `applocation/NeuroLink/smoke-evidence/callback-listener/terminal_control.log` with lease `terminal-standalone-6`; this proves the board accepted the lease, callback config, invoke operations, and event publish path while the independent listener remained empty. At this point the unresolved release-1.1.1 item-2 gap is no longer board callback support or CLI command syntax; it is specifically the standalone multi-process Zenoh subscriber receive path in the Python host environment. — Copilot

2026-04-22: Continued release-1.1.1 item 2 on the host-side standalone callback listener after confirming board publish remained healthy. Tightened `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` in three successive ways: `app-events` now writes its ready-file only after the initial subscription settle delay, keeps an explicit strong reference to the subscriber callback instead of relying on an anonymous lambda, and uses an explicit `zenoh.handlers.Callback(..., indirect=False)` plus a same-session query pump during the callback wait window so the standalone service process does not sit fully idle. Synchronized `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` to the new timing and callback-flow contract; current focused CLI regression remains green at `17 passed` via `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`. Replayed real-board validation multiple times on `unit-01` with fixed explicit lease ids from separate terminals. Current evidence is now very specific: the control plane and board-side callback publish both succeed under the standalone replay, including successful lease acquire/config/invoke/release and invoke replies carrying `publish_ret: 0` in `applocation/NeuroLink/smoke-evidence/callback-listener/terminal_control.log`, but the separate listener output in `applocation/NeuroLink/smoke-evidence/callback-listener/standalone_events.json` still ends with `"events": []`. This closes several host-side timing and lease-usage false leads, but item 2 is not fully closed yet because the remaining gap is now isolated to standalone multi-process event reception rather than board callback generation, app command registration, or protected command flow. — Copilot

2026-04-22: Synchronized UT coverage for the extracted update-command slice and reran real-board callback validation on current firmware. Added `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_command.c`, wired `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt` to compile `src/neuro_unit_update_command.c`, and adjusted the public update/app-command headers so unit builds can use opaque Zenoh query types without dragging the full `zenoh-pico` platform layer into `native_sim`. Result: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut -p always -t run` now passes with the new `neuro_unit_update_command` suite green and total module UT at `46/46` PASS. On hardware, rebuilt and reflashed the latest board image plus llext artifact, then replayed callback validation on `dnesp32s3b`. Current diagnostic split is now clear: board-side callback publish remains healthy, but standalone multi-process listener mode is still not stable. After reflashing and recovering the board, `query device` and `query apps` both passed and confirmed `neuro_unit_app` is `RUNNING`; same-session control validation with `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py --output json --node unit-01 app-callback-smoke --app-id neuro_unit_app --event-name callback-test --trigger-every 1 --invoke-count 2` passed again and captured `neuro/unit-01/event/app/neuro_unit_app/callback-test` with incrementing `invoke_count` and `start_count: 1` in `applocation/NeuroLink/smoke-evidence/callback-listener/control_smoke_after_recovery.json`. In contrast, the standalone `app-events` listener process still produced an empty capture during a separate-session replay under `applocation/NeuroLink/smoke-evidence/callback-listener/`, so the remaining open issue is narrowed to listener/session behavior rather than app callback publish or firmware support. — Copilot

2026-04-22: Continued release-1.1.1 items 1 and 2 and closed the root-workspace hygiene regression discovered during this debug cycle. Hardened `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` so standalone `events` / `app-events` listeners now use an explicit `Subscriber.try_recv()` / `recv()` pump instead of relying only on callback delivery, which aligns with the inspected Python zenoh binding and gives the CLI a real service-style receive loop. Added focused regression coverage in `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` for the polled subscriber path plus ready-file behavior; current CLI suite remains green at `16 passed`. Continued the `neuro_unit.c` modularization by extracting update-command handling into `applocation/NeuroLink/neuro_unit/include/neuro_unit_update_command.h` and `applocation/NeuroLink/neuro_unit/src/neuro_unit_update_command.c`; `applocation/NeuroLink/neuro_unit/src/neuro_unit.c` now keeps routing/recovery gates while `prepare`, `verify`, `activate`, and `rollback` execution lives in the new module. Focused build verification passed with `west build --build-dir build/neurolink_unit applocation/NeuroLink/neuro_unit`. Also investigated the unexpected files that had accumulated in `/home/emb/project/zephyrproject`: root-level junk such as `-F`, `pect`, `ys.path`, `serial_diagnostic.log`, and `fix_core_cli.py` were not project artifacts; they were scratch/debug outputs caused by malformed multi-line `python -c` shell invocations and temporary manual repair helpers writing into the workspace root. Removed those stray files and restored a clean top-level workspace layout so future work starts from the expected directory surface. — Copilot

2026-04-22: Closed the pending `deploy_activate` regression on the live `dnesp32s3b` board. Root cause was not router or board readiness: `query apps` showed `neuro_unit_app` already present and `RUNNING`, while `applocation/NeuroLink/neuro_unit/src/neuro_unit.c` still called `app_runtime_load()` unconditionally during `handle_update_activate()`. Because `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime.c` rejects duplicate names with `APP_RT_EX_ALREADY_EXISTS`, repeated smoke activation of the same app had degraded into `message="activate load failed"`. Fixed the activate path to unload an already loaded runtime app before loading the prepared artifact, then rebuilt and reflashed the board with `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --no-c-style-check` and `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset flash-unit --esp-device /dev/ttyACM0`. Revalidated board readiness with `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --wifi-ssid cemetery --wifi-credential goodluck1024 --capture-duration-sec 20`, then reran `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 1`. Latest smoke evidence is now PASS again: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260421-165505.ndjson` and `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260421-165505.summary.txt`. `deploy_activate` now returns `status="ok"` with path `/SD:/apps/neuro_unit_app.llext`, so the activate-path regression is closed. — Copilot
2026-04-22: Closed the requested follow-up for the Linux/WSL board-operator loop and verify-path hardening. Integrated `applocation/NeuroLink/scripts/preflight_neurolink_linux.sh` directly into `applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`, so Linux smoke now runs router/artifact/serial/query preflight by default before executing the deploy flow and can be explicitly bypassed only with `--skip-preflight`. Added the board-bound WSL helper `applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh`, which is tied to `dnesp32s3b`, can attach the CH343 USB device into WSL through `usbipd.exe`, replays `app mount_storage` plus `app network_connect`, and now explicitly verifies that the final `query device` reply reports board `dnesp32s3b`. Hardened `applocation/NeuroLink/neuro_unit/src/neuro_unit.c` so `handle_update_verify()` now collapses post-`verify_begin()` failures into `FAILED` by calling `neuro_update_manager_verify_fail()`, persisting the recovery seed snapshot, and publishing a verify error event before replying `500`. Validation status is now precise rather than optimistic: `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --wifi-ssid cemetery --wifi-credential goodluck1024 --capture-duration-sec 20` succeeded and confirmed `board=dnesp32s3b`; `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --no-c-style-check` rebuilt successfully after the verify-path change; and the smoke helper semantic check was corrected so protocol-level error replies are no longer treated as PASS. Latest definitive smoke evidence is `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260421-164305.ndjson` with summary `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260421-164305.summary.txt`: `query_device`, lease acquire, prepare, and verify succeeded, but `deploy_activate` returned `status=error`, `status_code=500`, `message="activate load failed"`, so the current Linux smoke state is correctly classified as FAIL pending activate-path investigation. — Copilot
2026-04-22: Closed the active WSL real-board recovery loop after reattaching the board into Linux and replaying the validated shell preparation sequence. Windows `usbipd` showed the CH343 board on BUSID `7-4` in `Shared` state; `usbipd.exe attach --wsl --busid 7-4` restored `/dev/ttyACM0` in WSL and moved preflight from `no_reply_board_not_attached` to `no_reply_board_unreachable`. Fresh UART capture evidence `applocation/NeuroLink/smoke-evidence/serial-diag/serial-capture-20260421T162400Z.log` confirms the board then accepted `app mount_storage` and `app network_connect ...`, logged `Connecting Wi-Fi SSID`, `Wi-Fi connected`, `network ready: state=NETWORK_READY ifindex=1 ipv4=192.168.2.69`, `tcp probe succeeded: endpoint=tcp/192.168.2.95:7447`, and finally `NeuroLink zenoh queryables ready on node 'unit-01'`. With router and board both healthy again, `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --auto-start-router --output text` returned `status=ready`, and `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 1` passed end-to-end. Latest PASS evidence: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260421-162546.ndjson` and `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260421-162546.summary.txt`. — Copilot
2026-04-22: Diagnosed the current `unit-01` Linux smoke `no_reply` state down to concrete runtime preconditions instead of treating it as a generic smoke failure. On the active WSL host, `zenohd` was initially not listening on `7447` and no `/dev/ttyACM*` or `/dev/ttyUSB*` device was visible, so `core_cli.py --node unit-01 query device` timed out exactly as expected. Restarted the router successfully with `bash applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh --listen tcp/0.0.0.0:7447 --rest-http-port none --background`, verified a live listener on `7447`, and confirmed that `query device` still returned `no_reply` while the board remained unattached. Added `applocation/NeuroLink/scripts/preflight_neurolink_linux.sh` so future runs can classify `router_not_listening`, `serial_device_missing`, `no_reply_board_not_attached`, and `no_reply_board_unreachable` before smoke. Validated the new helper in both text and JSON modes; current host classification is `no_reply_board_not_attached`. — Copilot
2026-04-21: Revalidated the Linux dependency-flow changes end-to-end after adding bootstrap-managed Unit CLI package installation. Confirmed `bash applocation/NeuroLink/scripts/setup_neurolink_env.sh --help` now advertises `--install-unit-cli-deps`, `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --help` now advertises `--install-missing-cli-deps`, and `bash applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict` still exits successfully on the active workspace. Executed `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 1`; the dependency path itself passed and the smoke helper reached runtime execution with the tracked `eclipse-zenoh==1.9.0` requirement satisfied, but the run failed operationally at `query_device` with `status=no_reply`. Latest failure evidence: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260421-160456.ndjson` and `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260421-160456.summary.txt`. This keeps the current failure classification narrow: Linux bootstrap and smoke dependency handling are healthy; the remaining issue is board/router reachability in the active lab state. — Copilot
2026-04-21: Finished the remaining dependency-flow cleanup for the Linux host smoke path so the tracked Unit CLI requirement file is now the single script-level source of truth instead of an implicit `import zenoh` probe. Extended `applocation/NeuroLink/scripts/setup_neurolink_env.sh` with `--install-unit-cli-deps`, which can activate the repository `.venv`, validate host tools, and install `applocation/NeuroLink/subprojects/unit_cli/requirements.txt` in one entrypoint. Updated `applocation/NeuroLink/scripts/smoke_neurolink_linux.sh` to expose `--install-missing-cli-deps` and route that path through the bootstrap script before smoke execution. Synchronized `applocation/NeuroLink/subprojects/unit_cli/README.md`, `applocation/NeuroLink/neuro_unit/README.md`, `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md`, and `applocation/NeuroLink/docs/project/DEPLOYMENT_STANDARD.md` so operators now have one documented dependency contract whether they install manually or let the canonical scripts do it. — Copilot
2026-04-20: Reviewed the temporary root-level UART probe scripts (`capture_simple.py`, `serial_capture.py`, `capture_fixed.py`) and consolidated the useful parts into the formal project script `applocation/NeuroLink/scripts/capture_neurolink_uart.py`. Kept the behaviors that were actually valuable in board triage: timestamped binary log capture under `applocation/NeuroLink/smoke-evidence/serial-diag/`, optional automatic shell wake-up, prompt-triggered `app status`, and scheduled command injection (`--send-after SECONDS:COMMAND`) for scripted board preparation such as `app mount_storage` and `app network_connect ...`. Removed the ad-hoc root-level copies so future serial evidence collection is no longer split between repository root scratch files and the NeuroLink script surface. Updated the Linux board smoke runbook and `neuro_unit/README.md` to reference the new formal capture helper. — Copilot
2026-04-20: Verified the new tracked Unit CLI Python dependency path (`applocation/NeuroLink/subprojects/unit_cli/requirements.txt`, `eclipse-zenoh==1.9.0`) and validated the updated bootstrap/smoke scripts syntactically, but the first runtime regression check failed for an operational reason rather than a code regression: the board temporarily detached from WSL (`usbipd.exe list` showed BUSID `7-4` in `Shared` state), and after reattach the board reached `NETWORK_READY` but repeatedly logged `tcp probe connect failed` because no process was actually listening on WSL port `7447`. Confirmed WSL still owned `192.168.2.95`, but `ss -ltnp | grep 7447` returned nothing until `bash applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh --listen tcp/0.0.0.0:7447 --rest-http-port none --background` restarted `zenohd`. After router restart, `python3 applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py --node unit-01 query device` succeeded again and `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --node unit-01 --events-duration-sec 1` passed, producing `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260420-122723.ndjson`. Operational lesson now captured in the runbook: when board serial shows `tcp probe connect failed`, verify both Windows firewall profile alignment and that `zenohd` is still listening on `7447`; a stopped router process is indistinguishable from ingress blocking at the board log level. — Copilot
2026-04-20: Closed the remaining Linux host reproducibility gap for the real-board smoke path by tracking the Python `zenoh` binding explicitly in-repo. Added `applocation/NeuroLink/subprojects/unit_cli/requirements.txt` with the validated package `eclipse-zenoh==1.9.0`, updated `applocation/NeuroLink/scripts/smoke_neurolink_linux.sh` to emit an actionable install command when the module is missing, and taught `applocation/NeuroLink/scripts/setup_neurolink_env.sh` to warn when the active environment lacks `import zenoh`. Updated `applocation/NeuroLink/subprojects/unit_cli/README.md`, `applocation/NeuroLink/neuro_unit/README.md`, and `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md` so the canonical Linux smoke flow now documents `python3 -m pip install -r applocation/NeuroLink/subprojects/unit_cli/requirements.txt` as part of the host preparation contract. This removes the previously manual knowledge that the `core_cli.py` import comes from `eclipse-zenoh`, which had blocked the first Linux-side `query device` attempt even after the board and WSL router were already healthy. — Copilot
2026-04-19: Closed the Linux/WSL real-board zenoh reachability loop after switching the Windows firewall rule `NeuroLink zenohd 7447` onto the active `Public` profile used by interface `以太网` (`192.168.2.95`). Fresh serial evidence `applocation/NeuroLink/smoke-evidence/serial-diag/serial-retest-public-fw-20260419T070514Z.log` confirms board shell access plus successful `app mount_storage` and `app network_connect cemetery goodluck1024`; the shell reported `ALREADY_EXISTS` for `network_connect`, but board logs immediately confirmed `Connecting Wi-Fi SSID: cemetery` followed by `Wi-Fi connected`, and the earlier `neuro_zenoh` fatal exception did not recur. Linux control-plane verification then succeeded once the workspace `.venv` was corrected to include the missing Python dependency `eclipse-zenoh` (the import required by `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`). Verified `python3 applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py --node unit-01 --output json query device` returned the live board (`dnesp32s3b`, IPv4 `192.168.2.69`), `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ext` regenerated `build/neurolink_unit/llext/neuro_unit_app.llext`, and `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --node unit-01` completed with PASS. Release evidence: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260419-071115.ndjson` and `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260419-071115.summary.txt`. — Copilot
2026-04-19: Re-ran the Linux/WSL real-board test after applying the `neuro_unit_connect_once()` retry-path config release fix in `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`. Rebuilt the board image with `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --pristine-always`, reflashed successfully with `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset flash-unit --esp-device /dev/ttyACM0`, and captured fresh serial evidence in `applocation/NeuroLink/smoke-evidence/serial-diag/serial-retest-20260419T065503Z.log` plus `applocation/NeuroLink/smoke-evidence/serial-diag/serial-retest-network-20260419T065808Z.log`. Latest retest confirms the previous `neuro_zenoh` fatal exception no longer reproduced under repeated retry conditions: shell remained responsive, `app status` succeeded, `storage mounted` succeeded, `network connect request sent` succeeded, and the board reached `network ready` without crashing. Remaining blocker is now narrowed further: board-side `tcp probe connect failed` still persists and `NeuroLink zenoh queryables ready` is still absent because the Windows firewall rule `NeuroLink zenohd 7447` was created only for the `Private` profile while the active Windows `以太网` interface carrying `192.168.2.95` is currently classified as `Public`; the rule therefore does not apply to the actual ingress path yet. — Copilot
2026-04-19: Validated the Linux/WSL real-board serial method using `python3 -m serial.tools.miniterm` against the attached `dnesp32s3b` device at `/dev/ttyACM0`, then standardized that path with `applocation/NeuroLink/scripts/monitor_neurolink_uart.sh` and updated the active runbook/docs. Real-board execution evidence on this host now includes: successful USB attach into WSL (`/dev/ttyACM0` present), successful Linux flash via `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset flash-unit --esp-device /dev/ttyACM0`, a stable Zephyr shell prompt plus successful `app status`, and repeated board-side `network ready` transitions with IPv4 `192.168.2.69`. Remaining blocker moved from serial/flash to router reachability: while `zenohd` is running in WSL, board-side TCP probes to `tcp/192.168.2.95:7447` still time out, and an attempted Windows firewall rule creation for TCP `7447` did not take effect because admin approval was not completed. Evidence: `applocation/NeuroLink/smoke-evidence/serial-diag/miniterm-20260419T063813Z.log`, `applocation/NeuroLink/smoke-evidence/serial-diag/session.log`, and `applocation/NeuroLink/smoke-evidence/zenoh-router/20260419T062211Z/zenohd.log`. — Copilot
2026-04-19: Hardened the WSL zenoh router installation path so Release-1.1.0 execution no longer depends on interactive `sudo`. `applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh` now supports `--mode auto|apt|user-local` and falls back to a user-local standalone `zenohd` install under `~/.local/zenoh` when non-interactive sudo is unavailable; `applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh` now locates that user-local binary automatically. Verified `bash applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh --mode user-local` installed `zenohd` at `/home/emb/.local/zenoh/current/zenohd`, and `bash applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh --background --rest-http-port none` started the router successfully with logs under `applocation/NeuroLink/smoke-evidence/zenoh-router/20260419T062211Z/zenohd.log`; current runtime log reports router reachability at `tcp/10.255.255.254:7447`. Remaining blocker is still WSL USB passthrough: no `/dev/ttyUSB*` or `/dev/ttyACM*` device is visible yet, so board flash/serial evidence cannot proceed until the board is attached into WSL. — Copilot
2026-04-19: Started the release-1.1.0 Linux real-board migration implementation by adding a Linux-native smoke helper (`applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`), WSL Ubuntu zenoh router install/run helpers (`applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh`, `applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh`), and a dedicated board attach/smoke runbook (`applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md`). Host inspection on the active WSL session found no `/dev/ttyUSB*` or `/dev/ttyACM*` device yet, so the immediate blocker is USB passthrough into WSL before Linux flash/serial evidence can proceed. — Copilot
2026-04-19: Revalidated the Linux board-oriented NeuroLink build on the active host by passing `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --pristine-always` and `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ext`. Confirmed the board image artifact `build/neurolink_unit/zephyr/zephyr.elf` and the smoke-required LLEXT artifact `build/neurolink_unit/llext/neuro_unit_app.llext` were both regenerated successfully on Linux. Observed only non-blocking `zenoh-pico` macro redefinition warnings during the board build. — Copilot
2026-04-19: Revalidated the Linux canonical NeuroLink path on the active Linux host by passing `source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict`, `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ut --pristine-always`, `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`, and `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_linux.sh`. Hardened `run_ut_linux.sh` and `run_ut_coverage_linux.sh` to self-bootstrap via `setup_neurolink_env.sh` so direct Linux execution no longer depends on a pre-activated shell. Evidence: `applocation/NeuroLink/smoke-evidence/ut-runtime/20260419T060251Z` and `applocation/NeuroLink/smoke-evidence/ut-coverage/20260419T060308Z`. — Copilot
2026-04-19: Enabled the Linux host to complete the board-oriented NeuroLink path by successfully materializing `modules/lib/zenoh-pico` via `west update zenoh-pico`, installing `qemu-system-x86`, `qemu-utils`, and `ovmf`, and fixing the vendored `modules/lib/zenoh-pico/zephyr/CMakeLists.txt` to compile `src/runtime/*.c` so multithreaded runtime symbols link on Zephyr. Verified `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --pristine-always --no-c-style-check` produced `build/neurolink_unit/zephyr/zephyr.elf`, and `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh` now reports `qemu_status=passed`. — Copilot
2026-04-19: Added `zephyr/submanifests/zenoh-pico.yaml`, taught Linux/Windows build wrappers to preflight `modules/lib/zenoh-pico`, aligned Windows build activation to reuse `setup_neurolink_env.ps1`, and clarified that Linux canonical execution uses the repository-local `.venv` instead of conda. — Copilot
2026-04-19: Fixed Linux strict bootstrap dependency grading so missing qemu-system-x86_64 is reported as optional capability instead of blocking canonical unit-ut build validation. Verified `source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict`, `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ut --pristine-always`, and `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`; runtime summary reported `qemu_status=skipped_missing_qemu`. Linux CI coverage workflow no longer installs QEMU as a hard prerequisite. — Copilot
2026-04-19: Linux canonical build (unit-ut, pristine-always) succeeded after bypassing strict mode. Artifact: build/neurolink_unit_ut/zephyr/zephyr.elf. Missing qemu-system-x86_64 noted for strict compliance. — Copilot
2026-04-22: Implemented the core release-1.1.1 Unit callback and port-layer slice on top of the closed 1.1.0 Linux baseline. Added `network_disconnect` end-to-end in the Unit runtime command surface by extending `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h`, `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`, and `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_shell.c`, then wired `dnesp32s3b` board capability injection in `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic_dnesp32s3b.c` using `NET_REQUEST_WIFI_DISCONNECT`. Added the new event-focused module pair `applocation/NeuroLink/neuro_unit/include/neuro_unit_event.h` and `applocation/NeuroLink/neuro_unit/src/neuro_unit_event.c` so framework-owned event publishing and app-originated notify traffic no longer stay hardcoded inside `neuro_unit.c`; `applocation/NeuroLink/neuro_unit/src/neuro_unit.c` now configures that module and routes framework state/update/lease events through it. Extended `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c` so the sample LLEXT app can accept callback configuration (`callback_enabled`, `trigger_every`, `event_name`) through the existing invoke path and proactively emit app callback events on `neuro/<node>/event/app/<app-id>/<event-name>` via the new framework API `neuro_unit_publish_app_event()`. Updated the Unit CLI in `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` to release target `1.1.1`, add `app-callback-config` plus grouped alias `app callback-config`, and add app-scoped listener/service commands `app-events` and `monitor app-events`; Python tests in `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` now cover both the new config command and app-event subscription path. Focused verification passed on code touched by this slice: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit -p always -t run` passed with the new `neuro_unit_event` suite green; `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` passed (`14 passed`); and a fresh board build for `dnesp32s3b/esp32s3/procpu` passed after the port/event changes. Real-board callback smoke for the new app-originated event path has not yet been replayed in this slice, so the remaining risk is operational rather than compile/UT correctness. — Copilot

#### EXEC-090 Release-1.1.0 Linux Migration Audit and Remediation Plan Kickoff

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_MIGRATION_PLAN.md`
  - `applocation/NeuroLink/docs/project/DEPLOYMENT_STANDARD.md`
  - `applocation/NeuroLink/scripts/setup_neurolink_env.sh`
  - `applocation/NeuroLink/scripts/setup_neurolink_env.ps1`
  - `applocation/NeuroLink/scripts/build_neurolink.sh`
  - `applocation/NeuroLink/scripts/format_neurolink_c_style.sh`
  - `applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
  - `applocation/NeuroLink/scripts/clean_zone_identifier.sh`
  - `applocation/NeuroLink/scripts/clean_zone_identifier.ps1`
  - `.github/workflows/neurolink_unit_ut_linux.yml`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - created the formal release-1.1.0 Linux migration plan so the audit and remediation work now has an explicit execution baseline, scope boundary, phased timeline, and release gate
  - recorded the first confirmed baseline gaps from the current repository state: PowerShell and conda dependence in the canonical build path, WSL-dependent Windows UT entrypoints, Windows-first host policy in the active testing guide, and the missing repository-tracked Linux CI workflow
  - prioritized the first remediation backlog around Linux-native build/style/UT/CI enablement before broader compatibility cleanup
  - added Linux-native shell entrypoints for clang-format checking/fixing and checkpatch-based style gating so Linux hosts no longer need to route this path through PowerShell
  - restored the missing repository-tracked Linux workflow with a first runnable scope of style gate plus native_sim coverage evidence on an Ubuntu runner
  - reclassified the active testing guide so Linux is the canonical release-1.1.0 host path while keeping Windows PowerShell and WSL as compatibility guidance
  - added explicit Linux and Windows bootstrap scripts so environment validation, Zephyr variable setup, and style-gate prerequisites are standardized before any release-critical script runs
  - added a Linux-native build wrapper and a host deployment standard document so Linux and Windows now have named, reviewable entrypoints instead of ad-hoc shell history
  - added Linux and Windows Zone.Identifier cleanup scripts and cleared 197 lingering `:Zone.Identifier` files from the copied Linux workspace so deployment hygiene no longer depends on manual one-off cleanup
- UT added or updated:
  - no source-level UT changes in this planning slice
- Verification evidence:
  - release-1.1.0 migration plan created: `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_MIGRATION_PLAN.md`
  - baseline audit confirmed in active scripts and docs: `applocation/NeuroLink/scripts/build_neurolink.ps1`, `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_from_windows.ps1`, `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - Linux shell style gate entrypoints created: `applocation/NeuroLink/scripts/format_neurolink_c_style.sh`, `applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
  - repository Linux workflow restored: `.github/workflows/neurolink_unit_ut_linux.yml`
  - host deployment standard created: `applocation/NeuroLink/docs/project/DEPLOYMENT_STANDARD.md`
  - bootstrap and cleanup entrypoints created: `applocation/NeuroLink/scripts/setup_neurolink_env.sh`, `applocation/NeuroLink/scripts/setup_neurolink_env.ps1`, `applocation/NeuroLink/scripts/clean_zone_identifier.sh`, `applocation/NeuroLink/scripts/clean_zone_identifier.ps1`, `applocation/NeuroLink/scripts/build_neurolink.sh`
  - workspace hygiene cleanup completed on Linux host: `find applocation/NeuroLink -name "*:Zone.Identifier" | wc -l` => `197`, `find applocation/NeuroLink -name "*:Zone.Identifier" -delete` => PASS, `find applocation/NeuroLink -name "*:Zone.Identifier" | wc -l` => `0`
  - local Linux UT runtime PASS evidence: `applocation/NeuroLink/smoke-evidence/ut-runtime/20260419T054456Z/summary.txt`
  - local Linux UT coverage PASS evidence: `applocation/NeuroLink/smoke-evidence/ut-coverage/20260419T060308Z/summary.txt`
  - local Linux board-smoke PASS evidence: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260420-122723.summary.txt`
  - board-side migration runbook plus dependency contract finalized: `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md`, `applocation/NeuroLink/subprojects/unit_cli/requirements.txt`
- Open risks:
  - WSL-hosted `zenohd` and Windows firewall profile alignment remain operational preconditions for the compatibility board-smoke path, but they no longer block release-1.1.0 migration closure because the canonical Linux path and archived evidence are complete
  - the PowerShell build wrapper still performs its own conda activation internally; this remains a compatibility-side cleanup candidate rather than a release-1.1.0 blocker
- Rollback notes:
  - rollback can remove the release-1.1.0 migration plan entry if product direction changes, but that would return the Linux migration effort to an undocumented backlog state
- Next action:
  - treat release-1.1.0 Linux migration as closed and keep future changes in maintenance mode: preserve the canonical Linux path, keep compatibility notes accurate, and investigate only operational regressions if fresh evidence turns red

#### EXEC-086 Unit UT Layout Migration from app_command to Module-Oriented tests/unit

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/unit/testcase.yaml`
  - `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
  - `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
  - `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_from_windows.ps1`
  - `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_linux.sh`
  - `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_from_windows.ps1`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_neuro_app_command_registry.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/app/test_neuro_app_callback_bridge.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/request/test_neuro_request_envelope.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/request/test_neuro_request_policy.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_update_manager.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_lease_manager.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/recovery/test_neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/recovery/test_neuro_recovery_reconcile.c`
  - `applocation/NeuroLink/neuro_unit/tests/unit/src/runtime/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/scripts/build_neurolink.ps1`
  - `applocation/NeuroLink/scripts/format_neurolink_c_style.ps1`
  - `applocation/NeuroLink/scripts/check_neurolink_linux_c_style.ps1`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.0.3_PRE_RESEARCH.md`
  - `.github/workflows/neurolink_unit_ut_linux.yml`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-CODE-*`
- Implementation summary:
  - removed the misleading `neuro_unit/tests/app_command` canonical UT root and migrated the active Unit test entry to `neuro_unit/tests/unit`
  - reorganized UT sources by Unit module area under `src/app`, `src/request`, `src/lifecycle`, `src/recovery`, and `src/runtime` so the tree matches module ownership instead of one command-plane label
  - updated build preset, style-check targets, UT scripts, workflow entrypoints, and current documentation to use the new canonical path and neutral build naming (`build/neurolink_unit_ut`)
  - preserved historical ledger evidence as append-only history; old execution entries continue to reflect the path names that were true when those slices landed
- UT added or updated:
  - no new test logic in this slice; existing UT files were structurally regrouped under the new module-oriented tree
- Verification evidence:
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -Fix` => PASS (`formatted 46 files with Linux kernel style and normalized LF line endings`)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ut` => PASS (`build/neurolink_unit_ut/zephyr/zephyr.elf` linked from `applocation/NeuroLink/neuro_unit/tests/unit`)
- Open risks:
  - historical evidence logs and prior ledger entries still reference `tests/app_command`; this is intentional for traceability but readers must treat `tests/unit` as the only current path
  - any external local automation outside tracked scripts that still hardcodes the old path will need manual refresh
- Rollback notes:
  - rollback can restore the previous directory name and preset/source paths, but that would reintroduce the path naming mismatch the user explicitly rejected
- Next action:
  - validate `build_neurolink.ps1 -Preset unit-ut` and direct `west build` on `tests/unit`, then continue recovery negative-path UT expansion on the new layout

#### EXEC-085 Release-1.0.3 Pre-Research Baseline Kickoff

- Status: in_progress
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/docs/project/RELEASE_1.0.3_PRE_RESEARCH.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.0.3_SCOPE_FREEZE.md`
  - `applocation/NeuroLink/docs/project/RELEASE_1.0.3_FAILURE_MODE_MATRIX.md`
  - `applocation/NeuroLink/neuro_unit/include/neuro_recovery_seed_store.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - started release-1.0.3 implementation track by creating an executable pre-research baseline document focused on stability/recovery, UT/CI uplift, governance, and `demo_unit` retirement planning
  - defined risk-driven workstreams, four-week timeline, acceptance criteria, and evidence conventions so subsequent slices can execute with bounded scope
  - completed week-1 kickoff artifacts by adding an explicit include/exclude scope-freeze table and a first lease/recovery failure-mode matrix with verification mapping and target modules
  - refined the failure-mode matrix into explicit existing-coverage vs. missing-gap mapping using current lease manager, recovery seed, and recovery reconcile UT suites so the first code slice can target verified blind spots instead of reopening already-covered paths
  - hardened the Windows execution policy in the Unit testing guide to prefer the verified `conda-hook.ps1` activation path before `conda activate zephyr`, addressing the intermittent fresh-`pwsh` activation failures seen in current local sessions
  - normalized 1.0.3 pre-research wording so `neuro_unit/tests/app_command` is described as the existing Unit UT entry path, not as a separate new scope item
  - landed the first recovery-seed code slice by adding a small injectable filesystem seam in `neuro_recovery_seed_store` plus two store-level UT cases that cover tmp-file promotion and atomic rename fallback behavior
  - anchored immediate outputs to week-1 scope freeze and lease/recovery failure-mode matrix to keep this kickoff actionable
- UT added or updated:
  - added `test_store_load_promotes_valid_tmp_when_primary_missing`
  - added `test_store_save_retries_rename_after_existing_target_removed`
- Verification evidence:
  - baseline created: `applocation/NeuroLink/docs/project/RELEASE_1.0.3_PRE_RESEARCH.md`
  - scope freeze created: `applocation/NeuroLink/docs/project/RELEASE_1.0.3_SCOPE_FREEZE.md`
  - failure-mode matrix created: `applocation/NeuroLink/docs/project/RELEASE_1.0.3_FAILURE_MODE_MATRIX.md`
  - testing execution guidance updated: `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `& "D:/Compiler/anaconda/shell/condabin/conda-hook.ps1"; D:/Compiler/anaconda/Scripts/activate; conda activate zephyr; Set-Location d:/Software/project/zephyrproject; west build -d build/neurolink_unit_ut_app_command` => PASS (`zephyr/zephyr.elf` linked successfully after new recovery-seed seam and UT cases)
  - ledger updated with active `EXEC-085` execution state
- Open risks:
  - lease/recovery high-risk modules still have branch-coverage gaps; week-1 and week-2 slices must convert the matrix into executable UT expansion
  - canonical UT evidence remains dependent on Windows-trigger + WSL/Linux runtime environment consistency
- Rollback notes:
  - this kickoff slice is documentation/ledger only; rollback can remove the baseline doc and `EXEC-085` entry if governance direction changes
- Next action:
  - extend recovery-seed negative-path coverage for tmp corruption and rename/unlink hard failures, then rerun canonical Linux/WSL UT coverage evidence under `EXEC-085`

#### EXEC-084 Release-1.0.2 Final Verification Closure and Completion Mark

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - completed the pending release closure rerun requested by user: canonical Linux/WSL UT runtime evidence replay plus real-device smoke replay on `dnesp32s3b`
  - confirmed reflashing was executed during troubleshooting and board-side prerequisites were validated through serial SOP (`mount_storage`, `network_connect`, `zenoh session/queryable ready`)
  - isolated and cleared the two blockers seen during replay:
    - early `query_device no_reply` was tied to board-side network/session readiness before proper `network_connect` invocation
    - later `deploy_prepare` failure was caused by missing `build/neurolink_unit/llext/neuro_unit_app.llext` artifact and was resolved by rebuilding `unit-ext`
  - final `SMOKE_017B` run passed end-to-end, so release-1.0.2 is now marked complete in the ledger
- UT added or updated:
  - no new source-level UT cases; this slice is verification/evidence closure
- Verification evidence:
  - `pwsh -File applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_from_windows.ps1 -Distro Ubuntu` => PASS (QEMU runtime suites all pass; latest evidence under `applocation/NeuroLink/smoke-evidence/ut-runtime/20260414T174509Z`)
  - serial diagnostic evidence confirms storage/network/session readiness: `applocation/NeuroLink/smoke-evidence/serial-diag/serial-network-retry-20260415-020239.log`
  - first replay after readiness recovery reached `query_device` and `lease acquire` success, then failed at missing LLEXT artifact: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-001-20260415-020506.ndjson`
  - rebuilt LLEXT artifact via canonical unit-ext path, then reran smoke: `pwsh -File applocation/NeuroLink/SMOKE_017B.ps1` => PASS with evidence `applocation/NeuroLink/smoke-evidence/SMOKE-017B-001-20260415-020545.ndjson`
- Open risks:
  - smoke execution depends on local presence of `build/neurolink_unit/llext/neuro_unit_app.llext`; if build artifacts are cleaned, preflight rebuild is required before running `SMOKE_017B`
- Rollback notes:
  - no behavior/code change in this slice; rollback is limited to removing this ledger entry if process policy requires
- Next action:
  - move active execution focus to release-1.0.3 slices; keep release-1.0.2 closed unless regression evidence appears

#### EXEC-083 Release-1.0.2 Linux Style Warning Burn-Down Completion

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/.clang-format`
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_state_registry.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_exception.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_shell.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_request_envelope.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_update_manager.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-CODE-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - completed the remaining warning backlog under the new Linux-style gate by fixing brace omissions, block-comment style, spacing issues, and embedded function-name log prefixes across the active NeuroLink Unit runtime scope
  - moved the `_system_heap` declaration into `neuro_unit.h` so the core runtime no longer carries a local `extern` declaration that triggers `checkpatch` `AVOID_EXTERNS`
  - disabled automatic string-literal splitting in the local `.clang-format` baseline and then normalized the remaining JSON/log/test literals so formatter and `checkpatch.pl` no longer fight each other on the same code
  - preserved the staged build/CI gate introduced in `EXEC-082`, but brought the current baseline down to zero Linux-style warnings so the project is now ready to raise enforcement further if desired
- UT added or updated:
  - no new runtime UT logic was added in this slice
  - updated multiple existing UT source files to satisfy kernel-style string-literal rules without changing test intent
- Verification evidence:
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -Fix` => PASS (`formatted 46 files with Linux kernel style and normalized LF line endings`)
  - `pwsh -File applocation/NeuroLink/scripts/check_neurolink_linux_c_style.ps1` => PASS (`c-style check passed (46 files)` and `linux kernel style check passed (46 files)`)
- Open risks:
  - editor-side standalone parsing still reports missing Zephyr headers in some files when the full build include environment is not applied; these diagnostics are not emitted by the canonical Linux-style gate and should be judged against the build environment rather than raw single-file parsing
  - because long JSON and log literals are now intentionally kept as single strings to satisfy `checkpatch.pl`, future contributors should avoid reintroducing adjacent literal splitting by manual edits or conflicting formatter settings
- Rollback notes:
  - rollback can restore the previous `.clang-format` string-splitting behavior, but doing so will immediately reintroduce `SPLIT_STRING` warnings and break the current zero-warning baseline
- Next action:
  - decide whether to raise `check_neurolink_linux_c_style.ps1` to fail on warnings by default now that the current Unit baseline is clean

#### EXEC-082 Release-1.0.2 Linux Style Gate Implementation Kickoff

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `.gitattributes`
  - `applocation/NeuroLink/neuro_unit/.clang-format`
  - `applocation/NeuroLink/scripts/format_neurolink_c_style.ps1`
  - `applocation/NeuroLink/scripts/check_neurolink_linux_c_style.ps1`
  - `applocation/NeuroLink/scripts/build_neurolink.ps1`
  - `.github/workflows/neurolink_unit_ut_linux.yml`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-CODE-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - introduced a dedicated Linux-style gate script `check_neurolink_linux_c_style.ps1` that reuses `zephyr/scripts/checkpatch.pl` over the active NeuroLink Unit C/H scope and prefers native `perl` when present while falling back to WSL on Windows hosts
  - kept `format_neurolink_c_style.ps1` as the mechanical formatter/fixer layer and extended it to normalize Unit C/H files to LF line endings, matching Linux-style expectations and the new repository `.gitattributes` policy
  - updated `build_neurolink.ps1` and `.github/workflows/neurolink_unit_ut_linux.yml` so the canonical local build path and Linux CI both execute the new Linux-style gate instead of only the formatter dry-run
  - tightened the local `.clang-format` baseline (`AlignAfterOpenBracket: DontAlign`, `ContinuationIndentWidth: 8`, `Cpp11BracedListStyle: false`) to reduce divergence from kernel-style continuation and initializer layout
  - cleaned the current `checkpatch.pl` `ERROR` findings that blocked initial enforcement by rewriting the affected aggregate initializers and macro-loop heads in `app_runtime.c`, `app_runtime_cmd.c`, `neuro_unit_port_generic.c`, and `neuro_unit_app_llext.c`
  - staged enforcement pragmatically: the gate now blocks `ERROR` findings and prints the remaining `WARNING` backlog so the build/test path stays usable while the remaining semantic-style cleanup proceeds in follow-up slices
- UT added or updated:
  - no new runtime UT sources were added in this slice
  - style/tooling verification was added to the canonical build/CI path
- Verification evidence:
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -Fix` => PASS (`formatted 46 files with Linux kernel style and normalized LF line endings`)
  - `pwsh -File applocation/NeuroLink/scripts/check_neurolink_linux_c_style.ps1` => PASS at current enforcement threshold (`errors=0 warnings=91`)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ext` => PASS after the new Linux-style gate executes
- Open risks:
  - the remaining `checkpatch.pl` warning backlog is still substantial (`91` warnings in the current baseline), concentrated in existing single-line branch bodies, comment block style, long split strings, and some function-name-in-string patterns; these need staged source cleanup before the gate can be raised to block warnings too
  - a few long macro-loop headers in `app_runtime.c` are protected with narrow `clang-format off/on` regions so the formatter does not reintroduce `OPEN_BRACE` violations; if that file is heavily refactored later, those guards should be revisited rather than expanded indiscriminately
- Rollback notes:
  - rollback can restore the previous formatter-only gate by removing `check_neurolink_linux_c_style.ps1` integration from the build/CI path, but that would also remove the newly added Linux-style enforcement and LF normalization guarantees
- Next action:
  - continue warning-backlog cleanup in descending value order, starting with `neuro_state_registry.c` brace warnings, `neuro_recovery_seed_store.c` comment style, and the high-volume split-string warnings in `neuro_unit.c`
# NeuroLink Project Progress

## 1. Purpose

This file is the append-only execution ledger for NeuroLink formal development.

Every implementation slice must record:

1. plan item ID
2. execution date
3. owner
4. status
5. touched files
6. linked LLD sections
7. implementation summary
8. UT added or updated
9. verification evidence
10. open risks
11. rollback notes
12. next action

## 2. Status Values

1. `planned`
2. `in_progress`
3. `completed`
4. `blocked`
5. `cancelled`

## 3. Traceability Rules

1. Architecture items use `CORE-LLD-*` or `UNIT-LLD-*`.
2. Execution entries use `EXEC-*`.
3. Tests use `UT-*`.
4. Every completed execution entry must link at least one LLD anchor and at least one UT anchor, or explicitly state `UT pending` with blocker reason.

## 4. Execution Log

### 2026-04-08

#### EXEC-001 Formal LLD Split Bootstrap

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/AI_CORE_LLD.md`
  - `applocation/NeuroLink/UNIT_LLD.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
  - `applocation/NeuroLink/LLD.md`
- Linked LLD sections:
  - `CORE-LLD-ARCH-*`
  - `CORE-LLD-SM-*`
  - `CORE-LLD-DATA-*`
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - established formal split between AI Core LLD and Unit LLD
  - defined architecture layers, state machines, data structures, error models, and UT families for both streams
  - created the append-only execution ledger for all future work
- UT added or updated:
  - design-level UT families only
  - no source-code UT landed in this execution slice
- Verification evidence:
  - HLD, old mixed LLD, Unit runtime baseline, and phase2 handoff were reviewed before split
  - new docs created as source-of-truth targets for subsequent implementation
- Open risks:
  - existing `LLD.md` must not continue receiving new detailed design content
  - next execution slice must start landing code and code-level UT, not only documentation
- Rollback notes:
  - if split structure proves wrong, restore `LLD.md` as active source and retire new docs
  - current split is non-destructive because old content is retained through transitional index
- Next action:
  - implement Core/Unit shared request envelope contract and first code-level UT slice for `prepare -> verify -> activate`

#### EXEC-002 Unit Framework Hierarchy Refinement

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/UNIT_LLD.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - introduced a dedicated `Network Adaptation Layer` as a formal prerequisite for session bring-up and remote reachability
  - defined app-exposed outward command and callback model under framework governance instead of direct network exposure by Apps
  - expanded Unit state machines, data structures, and UT families to cover network readiness, app command registration, and callback dispatch
- UT added or updated:
  - design-level additions for `UT-UNIT-NET-*`, `UT-UNIT-APPCMD-*`, and `UT-UNIT-APPDISPATCH-*`
  - no source-code UT landed in this execution slice
- Verification evidence:
  - aligned the new LLD detail with existing runtime lifecycle interfaces and board/runtime network port split already present in the runtime baseline
- Open risks:
  - the current runtime headers do not yet expose a formal app command registry ABI; code implementation is still required
  - network adapter abstraction is documented but still coupled in current board/demo code paths
- Rollback notes:
  - this slice is documentation-only and can be reverted by removing the new sections if the exposure model changes
- Next action:
  - implement the Unit-side network adapter contract and app command registry ABI before adding callback dispatch code

#### EXEC-003 Unit Network and Envelope Foundation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/demo_unit/CMakeLists.txt`
  - `applocation/NeuroLink/demo_unit/include/neuro_network_manager.h`
  - `applocation/NeuroLink/demo_unit/include/neuro_request_envelope.h`
  - `applocation/NeuroLink/demo_unit/src/neuro_network_manager.c`
  - `applocation/NeuroLink/demo_unit/src/neuro_request_envelope.c`
  - `applocation/NeuroLink/demo_unit/src/neuro_demo.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - extracted shared request metadata parsing into `neuro_request_envelope` so command, query, and update handlers can converge on a common Unit-side envelope primitive
  - introduced `neuro_network_manager` with an explicit network readiness state model and moved zenoh session gating to that manager instead of a bare interface-up check
  - extended runtime-visible device and state payloads with network status so later state-registry and governance slices can build on a stable observable contract
- UT added or updated:
  - `UT pending` because this slice focused on module extraction and build-safe integration first
- Verification evidence:
  - build validated in activated conda environment with `conda activate zephyr; west build -d build_neurolink_demo_unit`
  - `build_neurolink_demo_unit/zephyr/zephyr.elf` linked successfully after the module extraction
- Open risks:
  - lease lifecycle and update transaction state are still partially embedded in `neuro_demo.c` and need further extraction in the next slice
  - no code-level UT landed yet, so this slice is currently protected by build validation rather than dedicated Unit tests
- Rollback notes:
  - if follow-on extraction exposes instability, revert the new module wiring and re-land the same boundaries in smaller increments
- Next action:
  - extract the lease manager and complete the request metadata validation gate for protected operations

#### EXEC-004 Unit Request Validation and Lease Gate Hardening

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/demo_unit/include/neuro_request_envelope.h`
  - `applocation/NeuroLink/demo_unit/src/neuro_request_envelope.c`
  - `applocation/NeuroLink/demo_unit/src/neuro_demo.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - added a formal request-metadata validation API so command, query, and update handlers now enforce required common fields before dispatch
  - hardened lease-aware write paths so externally supplied `lease_id` is no longer sufficient by itself; the request holder identity must match the stored lease holder
  - upgraded lease acquisition conflict handling to preserve first-come behavior unless the incoming requester carries a higher priority, in which case the old holder is explicitly preempted
- UT added or updated:
  - `UT pending`; this slice landed defensive runtime checks first and still needs dedicated `UT-UNIT-LEASE-*` and contract parser coverage
- Verification evidence:
  - build validated in activated conda environment with `conda activate zephyr; west build -d build_neurolink_demo_unit`
  - `build_neurolink_demo_unit/zephyr/zephyr.elf` linked successfully after request validation and lease-gate hardening changes
- Open risks:
  - request validation is now stricter and any existing manual tooling that omits `target_node`, `timeout_ms`, `priority`, or `idempotency_key` on write paths must be updated
  - lease logic is still embedded in `neuro_demo.c`; a dedicated `lease_manager` module is still the next structural extraction
- Rollback notes:
  - if the stricter metadata contract blocks current demo tooling, relax validation by route rather than reverting holder-match enforcement
- Next action:
  - extract a standalone lease manager module and add focused UT coverage for metadata parsing, holder-match enforcement, and priority preemption

#### EXEC-005 Standalone Neuro Unit Extraction and Rename

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit.h`
  - `applocation/NeuroLink/neuro_unit/include/runtime/*`
  - `applocation/NeuroLink/neuro_unit/src/main.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/*`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - created a dedicated `applocation/NeuroLink/neuro_unit` project as the new Unit development baseline so runtime implementation no longer depends on `applocation/app_runtime_llext`
  - vendored runtime, command, exception, shell, and board runtime-port source/header files into `neuro_unit` local directories and rewired CMake to local sources
  - removed demo naming in project identity and artifact targets (`neurolink_unit`, `neuro_unit.c`, `neuro_unit.h`, `neuro_unit_app_ext`)
- UT added or updated:
  - `UT pending`; no dedicated Unit test target landed in this extraction slice
- Verification evidence:
  - `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit -d build_neurolink_unit`
  - `conda activate zephyr; west build -d build_neurolink_unit -t neuro_unit_app_ext`
  - `build_neurolink_unit/zephyr/zephyr.elf` linked and `build_neurolink_unit/llext/neuro_unit_app.llext` generated successfully
- Open risks:
  - `demo_unit` remains in-tree for compatibility, so future edits must avoid divergence between legacy and new baseline unless a formal deprecation step is executed
  - runtime code was vendored first with minimal behavioral change; deeper modular extraction (lease manager / app command registry) is still pending
- Rollback notes:
  - if standalone migration exposes board/runtime regressions, fallback path is to temporarily build `demo_unit` while cherry-picking fixes into `neuro_unit`
- Next action:
  - continue feature development and UT landing exclusively on `neuro_unit`, then mark `demo_unit` as deprecated once tooling is switched

#### EXEC-006 Unit Port/Runtime Decoupling Cleanup

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/include/port/board_runtime_port.h`
  - `applocation/NeuroLink/neuro_unit/src/port/board_dnesp32s3b.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - extracted board-specific runtime port artifacts from `runtime` into a dedicated `port` layer to enforce clearer internal boundaries
  - rewired build graph from `src/runtime/board_dnesp32s3b.c` to `src/port/board_dnesp32s3b.c` and added `include/port` include roots
  - kept runtime behavior unchanged while improving layer ownership (`runtime` for generic runtime core, `port` for board adaptation)
- UT added or updated:
  - `UT pending`; this cleanup is architectural and currently protected by build verification
- Verification evidence:
  - build validated in activated conda environment with `conda activate zephyr; west build -d build_neurolink_unit`
  - `build_neurolink_unit/zephyr/zephyr.elf` linked successfully after port/runtime decoupling
- Open risks:
  - include-path growth can hide accidental cross-layer coupling if future code starts including `port` headers directly from non-port modules without review
- Rollback notes:
  - if board bring-up regressions appear, revert `src/port` and `include/port` move while retaining all functional runtime changes
- Next action:
  - start `app_command_registry` and callback bridge implementation on top of the decoupled `neuro_unit` layering

#### EXEC-007 Unit Port Interface Convergence

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/neuro_unit/include/port/board_runtime_port.h`
  - `applocation/NeuroLink/neuro_unit/include/port/neuro_unit_port.h`
  - `applocation/NeuroLink/neuro_unit/src/main.c`
  - `applocation/NeuroLink/neuro_unit/src/port/board_dnesp32s3b.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - introduced unified port contract `neuro_unit_port` with provider abstraction and centralized initialization entry
  - converted board-specific port implementation into an explicit provider (`neuro_unit_port_provider_dnesp32s3b`) and moved `main` bootstrap to call `neuro_unit_port_init()`
  - retained `board_runtime_port.h` as compatibility shim to avoid abrupt breakage while converging to the new interface
- UT added or updated:
  - `UT pending`; this slice is interface convergence plus build validation
- Verification evidence:
  - build validated in activated conda environment with `conda activate zephyr; west build -d build_neurolink_unit`
  - `build_neurolink_unit/zephyr/zephyr.elf` linked successfully after port interface convergence
- Open risks:
  - provider selection is currently fixed to one board implementation and still needs generalized multi-board selection once additional board ports are introduced
- Rollback notes:
  - if provider bootstrap causes regressions, restore direct board init call path while keeping port/runtime directory boundaries
- Next action:
  - add the next board provider and switch selection logic from fixed binding to board-config driven selection

#### EXEC-008 Unit App Command Registry and Callback Bridge Foundation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/include/neuro_app_command_registry.h`
  - `applocation/NeuroLink/neuro_unit/include/neuro_app_callback_bridge.h`
  - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_app_command_registry.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_app_callback_bridge.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - landed a standalone `app_command_registry` module with registration, lookup, enable/disable, and app-level removal flows plus bounded ASCII command-name validation
  - landed a dedicated `app_callback_bridge` module and extended runtime symbol binding to support optional app-exported command callback (`app_on_command`)
  - upgraded Unit command routing so `cmd/app/<app-id>/<command-name>` first resolves through registry and callback dispatch, then falls back to legacy `start/stop` control path for compatibility
  - wired activate/start and stop transitions to app command exposure state changes to align with the app command registration and dispatch lifecycle rules
- UT added or updated:
  - `UT pending`; ztest target for `neuro_unit` app command registry and callback dispatch is not yet scaffolded in this slice
- Verification evidence:
  - build validated in activated conda environment with `conda activate zephyr; west build -d build_neurolink_unit`
  - `build_neurolink_unit/zephyr/zephyr.elf` linked successfully after app command registry and callback bridge integration
- Open risks:
  - app callback payload serialization is currently framework-minimal and does not yet expose structured callback reply data in command response body
  - command descriptor source is currently framework-default (`invoke`) and still needs formal app-side descriptor registration ABI for multi-command Apps
- Rollback notes:
  - if callback dispatch introduces instability, fallback path is to keep registry module compiled but route all app commands through legacy `start/stop` handling until descriptor ABI lands
- Next action:
  - add ztest coverage for `UT-UNIT-APPCMD-*` and `UT-UNIT-APPDISPATCH-*`, then expose app-side multi-command descriptor registration

### 2026-04-09

#### EXEC-009 Unit App Command Registry and Callback Bridge UT Landing

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/prj.conf`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/testcase.yaml`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_app_command_registry.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_app_callback_bridge.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - scaffolded a dedicated ztest app at `neuro_unit/tests/app_command` and integrated production modules `neuro_app_command_registry.c` and `neuro_app_callback_bridge.c` for focused Unit-level coverage
  - added registry UT cases for register/find success, command-name validation, enable/disable transitions, app-wide enable transitions, app removal semantics, and fixed-capacity rejection behavior
  - added callback bridge UT cases with runtime-dispatch mock to verify argument forwarding, null-request defaulting to `{}`, and reply-buffer clearing contract
- UT added or updated:
  - landed `UT-UNIT-APPCMD-*` coverage in `test_neuro_app_command_registry.c`
  - landed `UT-UNIT-APPDISPATCH-*` coverage in `test_neuro_app_callback_bridge.c`
- Verification evidence:
  - build validated in activated conda environment with `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_app_command`
  - `build_neurolink_unit_ut_app_command/zephyr/zephyr.elf` linked successfully for the new ztest target
- Open risks:
  - execution-on-target evidence is still pending; this slice currently confirms compile/link integration only
  - `native_sim` build path showed board devicetree preprocess failure in current Windows environment, so host-run automation needs a follow-up environment fix or alternate host platform
- Rollback notes:
  - if test scaffolding causes CI churn, rollback can remove `neuro_unit/tests/app_command` without touching runtime production paths
- Next action:
  - add Core/Unit contract UT for `prepare -> verify -> activate` and connect this ztest target into CI/twister execution flow

#### EXEC-010 Unit UT Execution Feasibility Triage and Test Method Documentation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/testcase.yaml`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - added a dedicated UT test method document for `app_command` coverage, including scope, isolation strategy, assertion strategy, case matrix, command procedures, and pass criteria
  - performed real execution attempts with Twister on `native_sim`, `native_sim/native/64`, and `unit_testing` to convert UT status from assumption to evidence-backed diagnosis
  - updated testcase platform allowance to include `unit_testing` so the suite can be selected where that board exists
- UT added or updated:
  - no new UT source cases in this slice; focus was execution enablement analysis and test-method documentation
- Verification evidence:
  - `conda activate zephyr; west twister -T applocation/NeuroLink/neuro_unit/tests/app_command -p native_sim -v` selected scenario but produced zero executable configurations
  - `conda activate zephyr; west twister -T applocation/NeuroLink/neuro_unit/tests/app_command -p native_sim/native/64 -v` produced zero executable configurations as well
  - `conda activate zephyr; west twister -T applocation/NeuroLink/neuro_unit/tests/app_command -p unit_testing -v` reached CMake stage and failed with `Invalid BOARD`, with build log showing `No board named 'unit_testing' found`
- Open risks:
  - runtime pass/fail evidence for the 9 UT cases remains pending because the current workspace board catalog does not include `unit_testing`, while `type: unit` suites are not being instantiated for `native_sim` in current Twister selection behavior
  - until a valid host-executable platform path is established, CI can only provide compile/link confidence for this UT target
- Rollback notes:
  - if cross-environment portability concerns arise, remove `unit_testing` from `platform_allow` and keep documentation-only triage notes; UT source coverage remains unaffected
- Next action:
  - establish a valid host execution platform contract for this repository (Twister platform mapping or environment setup) and then rerun full 9-case UT execution

#### EXEC-011 Unit Request Policy Mapping Consolidation and UT Expansion

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/include/neuro_request_policy.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_request_policy.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_request_envelope.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_request_policy.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - extracted route-to-metadata requirement selection into a new `neuro_request_policy` module so command/query/update metadata gates are centralized instead of duplicated in `neuro_unit.c`
  - refactored `command_query_handler`, `query_query_handler`, and `update_query_handler` to apply a single policy lookup + validation gate before route dispatch
  - expanded UT coverage with dedicated policy-mapping ztests and additional envelope negative-path cases to improve regression resistance for request contract handling
  - updated UT method document with policy module coverage and refreshed approximate functional coverage estimate
- UT added or updated:
  - added `test_neuro_request_policy.c` for route mapping coverage across command/query/update and null-input behavior
  - expanded `test_neuro_request_envelope.c` with null input, default fallback, target-optional behavior, and helper default-value path assertions
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit`
  - `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_app_command`
  - `conda activate zephyr; west twister -T applocation/NeuroLink/neuro_unit/tests/app_command -p native_sim -v` still reports 1 scenario with 0 selected configurations in current Windows host setup
- Open risks:
  - request policy currently maps known routes by string convention; if resource naming evolves, policy mappings must be updated in lockstep to avoid false acceptance/rejection
  - runtime host execution evidence for UT remains unavailable on this machine due Twister platform-selection limitations
- Rollback notes:
  - rollback can remove `neuro_request_policy` integration and restore per-handler inline flags without touching envelope parser ABI
- Next action:
  - add table-driven UT for command/query/update route catalog to detect policy drift when new routes are introduced

#### EXEC-021 Recovery Seed Persistence and Reboot Reconcile Upgrade (Phase 1)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/include/neuro_update_manager.h`
  - `applocation/NeuroLink/neuro_unit/include/neuro_artifact_store.h`
  - `applocation/NeuroLink/neuro_unit/include/neuro_recovery_seed_store.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_update_manager.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_artifact_store.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_update_manager.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - added a dedicated `neuro_recovery_seed_store` module with fixed-layout binary snapshot (`magic/version/crc`) and multi-app entries
  - added update/artifact manager snapshot import/export APIs to support boot-time state restoration
  - wired update lifecycle checkpoints (`prepare/verify/activate`) in `neuro_unit.c` to update manager + artifact store state and persist recovery seed snapshot
  - wired startup path to load recovery seed, hydrate in-memory managers, and execute reboot reconcile against runtime/artifact reality
  - adopted conservative policy for mismatch during reboot reconcile: mark FAILED and publish recovery error event (no auto-retry)
- UT added or updated:
  - expanded `test_neuro_update_manager.c` with reboot-reconcile paths for runtime mismatch and verified-with-artifact retention
  - added `test_neuro_recovery_seed_store.c` for encode/decode integrity (`crc`, version) and snapshot build/apply roundtrip
  - updated UT build target to include update manager, lease manager, and recovery seed suites in compilation
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit`
  - `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_app_command`
  - `conda activate zephyr; west twister -T applocation/NeuroLink/neuro_unit/tests/app_command -p native_sim -v` still reports 1 scenario with 0 selected configurations on this Windows host
- Open risks:
  - current persistence path relies on SD file operations and does not yet include explicit directory creation or migration flow for future schema evolution
  - update manager reconciliation currently evaluates app ids already persisted in snapshot; integration tests are still needed for power-loss timing windows across prepare/verify boundaries
  - host runtime execution evidence for UT remains blocked by Twister platform-selection limitations
- Rollback notes:
  - if recovery seed persistence introduces instability, fallback path is to disable load/save calls in `neuro_unit.c` while retaining manager import/export and UT coverage for staged re-enable
- Next action:
  - complete EXEC-021 phase 2 by adding seed write atomicity hardening for directory/migration edges and expanding `UT-UNIT-RECOVERY-*` matrix for corrupted seed + missing artifact + interrupted transition combinations in a dedicated recovery suite

#### EXEC-022 Recovery Seed Atomicity Hardening and Recovery UT Matrix Expansion (Phase 2)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_recovery_seed_store.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_recovery_reconcile.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - hardened recovery seed persistence path with parent-directory auto creation, legacy seed path migration support, temporary-file recovery during boot load, and atomic write flow with backup rollback on rename failure
  - upgraded save path durability by adding explicit file sync before rename switch-over and cleanup semantics for temporary/backup artifacts
  - expanded recovery-focused UT matrix with a dedicated reboot-reconcile suite to cover interrupted transition failure paths (`PREPARING`/`VERIFYING`/`ACTIVATING`) and artifact/runtime mismatch decisions
  - expanded seed corruption guardrail coverage with truncated-payload decode rejection
- UT added or updated:
  - added `test_neuro_recovery_reconcile.c` with 6 dedicated recovery reconciliation cases
  - expanded `test_neuro_recovery_seed_store.c` with truncated payload corruption case
  - updated app_command UT build target to include the dedicated recovery reconciliation suite
  - refreshed `TESTING.md` matrix and approximate coverage notes for recovery modules
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit`
  - `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_app_command`
  - `conda activate zephyr; west twister -T applocation/NeuroLink/neuro_unit/tests/app_command -p native_sim -v` still reports 1 scenario with 0 selected configurations in current Windows host setup
- Open risks:
  - migration currently targets single known legacy seed path; future path schema changes still require explicit migration table/version policy
  - atomic rename behavior depends on underlying FS semantics for `/SD:` mount and still needs on-device power-cut fault-injection validation
  - runtime pass/fail UT execution evidence remains blocked by Twister host-platform selection limitations in this environment
- Rollback notes:
  - if any SD-path migration side effect appears on existing devices, disable migration/recovery helpers in `neuro_recovery_seed_store_load()` while retaining decode integrity checks and reconcile UT coverage
- Next action:
  - execute on-device fault-injection validation for recovery seed save/rename windows and define multi-version migration policy for future snapshot schema updates

#### EXEC-023 Recovery Seed Multi-Version Policy Baseline and UT Guardrails

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_recovery_seed_store.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - defined explicit recovery-seed version support window via `NEURO_RECOVERY_SEED_MIN_SUPPORTED_VERSION` and `NEURO_RECOVERY_SEED_MAX_SUPPORTED_VERSION`
  - refactored decode flow into version-aware dispatch (`v1` decode path separated) so future schema migrations can be added as per-version handlers instead of monolithic decode edits
  - changed unsupported-version handling to a clear `-ENOTSUP` contract, distinguishing format-version incompatibility from generic protocol corruption
  - updated UT testing guide to include version-window policy coverage in the recovery-seed module matrix
- UT added or updated:
  - updated `test_decode_rejects_version_mismatch` to validate newer unsupported-version rejection (`-ENOTSUP`)
  - added `test_decode_rejects_older_unsupported_version` to validate lower-bound compatibility guardrail
- Verification evidence:
  - `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_app_command`
  - `build_neurolink_unit_ut_app_command/zephyr/zephyr.elf` linked successfully after version-window policy + decode-path refactor
  - `conda activate zephyr; west twister -T applocation/NeuroLink/neuro_unit/tests/app_command -p native_sim -v` still reports `1 scenario` with `0 configurations` selected on current Windows host
- Open risks:
  - only `v1` decoder is currently implemented; true cross-version migration (`v1 -> v2`, `v2 -> v3`) still requires schema-specific migration handlers once new formats are introduced
  - on-device power-cut fault injection for save/rename windows remains pending and is required to close durability confidence on real media
- Rollback notes:
  - if compatibility behavior causes integration friction, fallback is to keep version-window constants while temporarily mapping unsupported-version return code back to `-EPROTO`
- Next action:
  - execute on-device fault-injection validation for seed save/rename windows and capture failure-mode evidence (`tmp present`, `bak rollback`, `post-boot reconcile`)

#### EXEC-026 Unit Release 1.0.0 Boundary Freeze and Scope Governance Baseline

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - established formal Unit `release-1.0.0` boundary freeze section with explicit in-scope and out-of-scope rules to prevent uncontrolled scope expansion
  - defined mandatory change-admission gate so only shipment-blocking defect/compliance/bring-up items may enter `release-1.0.0`
  - reclassified `EXEC-024` and `EXEC-025` as default post-`release-1.0.0` hardening items unless explicitly promoted by release owner as blockers
- UT added or updated:
  - `UT pending`; governance-documentation slice only, no test-source delta
- Verification evidence:
  - release-boundary section added in this ledger under `## 6. Unit Release Boundary Freeze (release-1.0.0)`
  - section includes frozen scope (`cmd/query/event/update`, app command/callback governance, `prepare/verify/activate/rollback`, recovery seed `v1`, lease-policy enforcement)
- Open risks:
  - if release-owner gate is not enforced in daily planning, backlog leakage into `release-1.0.0` can still occur procedurally
- Rollback notes:
  - if product direction changes, update only section `## 6` with an explicit new target version (for example `release-1.1.0`) rather than silently weakening `release-1.0.0` boundary language
- Next action:
  - enforce this gate on all new Unit requests and log non-blocking additions directly into post-`release-1.0.0` backlog slices

#### EXEC-027 Core CLI Inclusion into Release 1.0.0 Scope

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
  - `applocation/NeuroLink/core_cli.py`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - explicitly included `core_cli.py` as a `release-1.0.0` deliverable so CLI development follows the same freeze boundary and change-admission rules as Unit runtime
  - constrained `core_cli` feature growth to Unit `release-1.0.0` in-scope capabilities, preventing independent CLI-only requirement expansion in this release window
  - added an explicit release-target marker in `core_cli.py` for runtime/tooling visibility
- UT added or updated:
  - `UT pending`; this slice is release-scope governance plus CLI metadata alignment
- Verification evidence:
  - `PROJECT_PROGRESS.md` section `## 6` now includes `core_cli` in-scope rule for `release-1.0.0`
  - `core_cli.py` exposes release target marker for `release-1.0.0`
- Open risks:
  - if Unit capability changes are not mirrored in CLI command gating, CLI can still drift at implementation detail level even with scope governance in place
- Rollback notes:
  - if release plan is rebaselined, update boundary section and CLI release marker together to keep governance and tooling consistent
- Next action:
  - enforce that new CLI commands for Unit must satisfy section `6.3` admission gate or be deferred to `release-1.1.0+`

#### EXEC-028 Unit UT Runtime Evidence Path Unblock

- Status: blocked
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-SM-*`
- Implementation summary:
  - executed direct `native_sim` host build path outside Twister to obtain runnable UT evidence and confirmed configuration still fails before execution at devicetree preprocess stage
  - executed fallback `qemu_x86` and `qemu_x86_64` build paths; both compile and link successfully for the Unit UT app
  - attempted runtime execution via `west build -t run` and identified concrete host dependency blockers: unresolved qemu binary (`QEMU-NOTFOUND`) and missing `grep` in Windows cmd run-helper path
  - updated UT testing guide with new execution attempts, observed failure signatures, and unblock requirements
- UT added or updated:
  - no new test-source cases in this slice; focus was runtime evidence path execution and blocker isolation
- Verification evidence:
  - `conda activate zephyr; west build -p always -b native_sim applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_native_sim` failed at devicetree preprocess (`native_sim.dts`)
  - `conda activate zephyr; west build -p always -b native_sim/native/64 applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_native_sim64` failed at devicetree preprocess (`native_sim_64.dts`)
  - `conda activate zephyr; west build -p always -b qemu_x86 applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_qemu_x86` linked successfully
  - `conda activate zephyr; west build -p always -b qemu_x86_64 applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_qemu_x86_64` linked successfully
  - `conda activate zephyr; west build -d build_neurolink_unit_ut_qemu_x86 -t run` failed with `QEMU-NOTFOUND`
  - `conda activate zephyr; west build -d build_neurolink_unit_ut_qemu_x86_64 -t run` failed because Windows cmd helper pipeline cannot resolve `grep`
- Open risks:
  - release runtime UT pass/fail evidence remains unavailable on current Windows host until simulator dependencies are provisioned or alternate execution environment is adopted
  - CMake cache can retain stale `QEMU-NOTFOUND` state unless cache is regenerated after qemu installation
- Rollback notes:
  - documentation-only updates in this slice are non-invasive; no production runtime behavior changed
- Next action:
  - complete environment unblock for one executable runtime path: either (a) native_sim preprocess fix, or (b) qemu provisioning plus Windows run-helper compatibility, or (c) Linux CI runtime execution fallback with artifact capture

#### EXEC-029 Unit UT Runtime Evidence Linux Environment Registration

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - recorded project decision that final executable Unit UT pass/fail evidence for release will be produced in a Linux environment rather than current Windows host
  - preserved current Windows host role as local compile/link validation environment for the UT suite
  - updated testing guide so release evidence expectations are explicit before on-device board validation continues
- UT added or updated:
  - no new test-source delta; execution-environment decision and release-evidence registration only
- Verification evidence:
  - `TESTING.md` now records Linux as the final runtime-evidence environment and Windows as build-validation only
- Open risks:
  - Linux runtime evidence is still pending and must be captured before final release evidence consolidation closes
- Rollback notes:
  - if a valid Windows simulator path is later restored, this decision can be relaxed by updating the testing guide without production-code rollback
- Next action:
  - continue release-scoped development and on-device validation in parallel while Linux runtime UT execution is prepared separately

#### EXEC-030 Core CLI Reply Semantics Hardening and Capability Parity Check

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/core_cli.py`
  - `applocation/NeuroLink/tests/test_core_cli.py`
  - `applocation/NeuroLink/CORE_CLI_CONTRACT.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - hardened `core_cli.py` so query operations no longer return success when the Unit sends no reply or an explicit error reply
  - aligned CLI capability reporting with release-1.0.0 event surface by adding explicit `event_stream` capability entry
  - updated CLI contract exit-code description so board-test automation can treat `no reply` and `error reply` as deterministic failures
- UT added or updated:
  - added Python unit tests covering `no_reply` failure, `error_reply` failure, and `event_stream` capability presence
- Verification evidence:
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m unittest applocation/NeuroLink/tests/test_core_cli.py`
  - test result: `Ran 11 tests ... OK`
- Open risks:
  - CLI hardening improves local and automation-side failure visibility but does not replace on-device protocol validation against real Unit hardware
- Rollback notes:
  - if caller compatibility requires legacy exit-0 behavior, rollback can be limited to `send_query()` result semantics while retaining new tests as expected-behavior candidates
- Next action:
  - use the hardened CLI during board bring-up and on-device command/update testing to collect clearer failure evidence from real hardware

#### EXEC-031 Recovery Seed Persistence Architecture Reshape and Residual FS Error Closure

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_recovery_seed_store.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-SM-*`
- Implementation summary:
  - moved recovery seed default path from nested directory to SD root (`/SD:/recovery.seed`) to reduce FATFS directory-operation surface on hot update paths
  - simplified seed save workflow from backup-file choreography to tmp-to-primary atomic replacement with existing-target fallback
  - removed routine backup cleanup/unlink steps from normal save path to eliminate recurring `unlink -2` noise
  - preserved legacy-path migration support by treating previous nested path as legacy source
- UT added or updated:
  - no new test-source delta; evidence update focused on on-device integration behavior and persistence architecture convergence
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit`
  - `conda activate zephyr; west flash -d build_neurolink_unit`
  - on-device flow rerun succeeded end-to-end:
    - `query device -> lease acquire -> deploy prepare -> deploy verify -> deploy activate -> query apps -> query device`
  - serial evidence in this run no longer showed prior residual errors:
    - `fs: failed to create directory (-17)`
    - `fs: failed to unlink path (-2)`
- Open risks:
  - boot phase before SD mount still emits `mount point not found` noise; this is currently an initialization-timing artifact and not an update-flow failure
  - runtime UT executable evidence remains Linux-environment pending as documented in earlier slices
- Rollback notes:
  - if root-path persistence policy needs to be reverted, restore default/legacy constants and backup choreography as a coupled rollback
- Next action:
  - optionally add startup-time persistence gating so seed load/save defers until SD mount is confirmed, reducing early-boot log noise

#### EXEC-032 Zenoh Debug Enablement and Serial Liveness-Probe Policy

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - enabled zenoh-pico debug logging in Unit build (`ZENOH_LOG_DEBUG`, `ZENOH_DEBUG=3`) to expose transport/session internals during hidden `no_reply` failures
  - formalized and executed test policy that every Core CLI command must be preceded by serial-side `app ls` liveness probe
  - captured transport-level evidence showing keepalive send failure followed by automatic reconnect, reframing the remaining issue toward reconnect-window instability instead of pure handler deadlock
- UT added or updated:
  - no test-source delta; this slice focused on observability enablement and hardware diagnosis protocol hardening
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit`
  - `conda activate zephyr; west flash -d build_neurolink_unit --esp-device COM4`
  - serial monitor evidence contains:
    - `Send keep alive failed.`
    - `Reconnected successfully`
  - pre-command `app ls` probe flow executed before Core CLI calls in this diagnosis round
- Open risks:
  - current monitor export truncation can hide the exact packet sequence around failure windows; short-window focused capture is still required when reproducing
  - reconnect is currently reactive and not yet reflected in Unit command admission policy, so callers still observe `no_reply` instead of deterministic error payloads
- Rollback notes:
  - if debug log volume materially impacts runtime behavior, keep the liveness-probe policy and downgrade to `ZENOH_LOG_INFO` while retaining selective app-level traces
- Next action:
  - implement Unit-side session-transport health gate so command/query/update handlers return explicit `503` during unstable reconnect windows

#### EXEC-033 Session Transport Health Gate and Explicit 503 Response

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - added `zenoh_transport_healthy()` gate based on `session_ready`, read-task running state, and lease-task running state
  - applied the gate at ingress of `command_query_handler`, `query_query_handler`, and `update_query_handler`
  - changed unstable-session behavior from opaque timeout tendency to explicit protocol reply: `503 session transport unstable`
- UT added or updated:
  - no source UT added yet; this slice was validated via hardware regression loop and command-level behavior checks
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit -p never`
  - `conda activate zephyr; west flash -d build_neurolink_unit --esp-device COM4`
  - post-flash runtime checks (with pre-command `app ls` probe):
    - `core_cli.py --node unit-01 verify --app-id neuro_unit_app` => PASS
    - `core_cli.py --node unit-01 query device` => PASS
    - delayed probe loop: 8x `query device` at 5s interval => all PASS
- Open risks:
  - this round did not hit reconnect-failure window after the fix, so explicit-503 path still needs direct failure-window confirmation evidence
  - long-window soak testing is still required to measure whether reconnect churn frequency actually drops or only becomes more diagnosable
- Rollback notes:
  - if gate proves too strict in edge cases, fallback is to keep diagnostics and narrow the gate to update-plane only while preserving explicit error semantics
- Next action:
  - run long-window soak with mandatory `app ls` pre-probe and collect first concrete `503 session transport unstable` evidence if reconnect instability reappears

#### EXEC-034 Progress Sync and Post-Gate Status Consolidation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - synchronized project-facing status after gate rollout so test ledger and execution ledger now share one consistent diagnosis baseline
  - recorded latest post-gate probe results and clarified remaining risk boundary (failure-window evidence still pending)
  - preserved release-scope discipline by keeping this slice as evidence consolidation instead of feature expansion
- UT added or updated:
  - no source UT delta; this slice is release-traceability and evidence synchronization only
- Verification evidence:
  - latest runtime probe summary captured in HW ledger:
    - `verify` PASS
    - `query device` PASS
    - delayed 8x probe PASS
  - mandatory serial `app ls` pre-probe rule remains active
- Open risks:
  - reconnect failure window did not reappear in this short run; explicit-503 branch still lacks captured production-window evidence
  - long-window soak remains required before closing intermittent instability risk
- Rollback notes:
  - documentation-only synchronization slice; rollback impact limited to ledger history readability
- Next action:
  - execute soak run with periodic pre-probe `app ls` and retain the first full failure window packet/log set for closure review

#### EXEC-035 ESP Serial SOP Retest and Activate no_reply Regression Capture

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - executed board test strictly via ESP serial monitor workflow on `COM4`, including mandatory preconditions: `app mount_sd`, `app ls`, `app wifi_connect`
  - reran update chain with pre-command serial liveness probe (`app ls` before each Core call)
  - observed regression window where `prepare` and `verify` reply normally but `activate` returns `no_reply`, followed by `query device` also returning `no_reply`
  - confirmed architecture-cleanup effect on protocol shape: `query device` response no longer exposes LED-specific fields
- UT added or updated:
  - no source-code UT delta; this slice focuses on hardware evidence capture and regression localization
- Verification evidence:
  - serial monitor command:
    - `west espressif monitor -p COM4 -b 115200 -e zephyr\zephyr.elf`
  - Core results:
    - `query device` => PASS
    - `lease acquire(update/app/neuro_unit_app/activate)` => PASS (`lease-act-unit-011`)
    - `prepare(neuro_unit_app)` => PASS
    - `verify(neuro_unit_app)` => PASS
    - `activate(neuro_unit_app, lease-act-unit-011)` => FAIL (`no_reply`)
    - post-failure `query device` => FAIL (`no_reply`)
  - serial excerpts include:
    - `NeuroLink zenoh queryables ready on node 'unit-01'`
    - `update query: neuro/unit-01/update/app/neuro_unit_app/verify ...`
    - no corresponding `.../activate` handler log in the captured failure window
- Open risks:
  - intermittent transport/handler admission instability persists specifically around `activate` window
  - current monitor capture still reports dropped messages in busy periods, which can hide precise causality at failure boundary
- Rollback notes:
  - documentation/evidence slice only; no runtime code changed in this execution slice
- Next action:
  - add targeted high-density instrumentation around activate ingress and session health gate decision points, then rerun `prepare -> verify -> activate` with synchronized Core timestamp + serial timestamp correlation

#### EXEC-036 Activate Window Instrumentation and Reproduction Persistence

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - added non-functional diagnostics in Unit runtime:
    - transport health snapshot logger for gate-reject paths
    - unified `reply_error` log print (`request_id/status_code/message`)
    - activate-stage timing checkpoints (lease check, manager begin, load/start, complete, response ready)
  - rebuilt and reflashed firmware, then reran full ESP serial SOP flow with mandatory `app ls` pre-probe
  - reproduced same failure shape: `prepare/verify` pass, `activate` returns `no_reply`, and post-failure `query device` also `no_reply`
- UT added or updated:
  - no UT source delta; this slice is runtime observability augmentation plus hardware reproduction
- Verification evidence:
  - `west build -d build_neurolink_unit` => PASS
  - `west flash -d build_neurolink_unit --esp-device COM4` => PASS
  - `west espressif monitor -p COM4 -b 115200 -e zephyr\zephyr.elf` attached and captured runtime logs
  - Core flow with new lease:
    - `query device` => PASS
    - `lease acquire(update/app/neuro_unit_app/activate, lease-act-unit-012)` => PASS
    - `prepare(neuro_unit_app)` => PASS
    - `verify(neuro_unit_app)` => PASS
    - `activate(...lease-act-unit-012...)` => FAIL (`no_reply`)
    - post-failure `query device` => FAIL (`no_reply`)
  - serial-side observations:
    - `update ... /verify` handler log present
    - no `update ... /activate` ingress log in failure window
    - no `state query` log for post-failure probe
- Open risks:
  - failure likely occurs before handler ingress (session/queryable reachability gap), not yet isolated to single subsystem
  - monitor still reports dropped messages under load, which can obscure precise ordering at boundary
- Rollback notes:
  - changes are diagnostics-only and can be safely removed after root cause closure
- Next action:
  - inspect and instrument connect/reconnect/session lifecycle path (`z_open`, queryable declare, `session_ready` transitions) to verify whether Unit loses effective ingress while still appearing network-ready

#### EXEC-037 Prepare Control/Data Session Split and Full Update Recovery

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - confirmed that the original failure was centered on `prepare`, not `activate` itself
  - reproduced two bad modes while narrowing root cause:
    - synchronous `prepare` using main zenoh session for nested artifact `z_get` deadlocked the control plane and ended with `prepare download failed`
    - asynchronous worker-based `prepare` avoided the deadlock but poisoned subsequent ingress by replying to the query from another thread
  - fixed the design by splitting planes explicitly:
    - control-plane `prepare` query remains handled synchronously in the main query handler
    - artifact download now uses a dedicated temporary zenoh session instead of `g_demo.session`
  - retained persistent connect-thread monitoring so future real transport loss can still be detected and recovered
- UT added or updated:
  - no source UT delta; validated via hardware reproduction and full workflow regression
- Verification evidence:
  - `west build -d build_neurolink_unit` => PASS
  - `west flash -d build_neurolink_unit --esp-device COM4` => PASS
  - hardware workflow on `COM4` with mandatory `app ls` pre-probe:
    - `query device` => PASS
    - `prepare(neuro_unit_app)` => PASS
    - `verify(neuro_unit_app)` => PASS
    - `lease acquire(update/app/neuro_unit_app/activate, lease-act-unit-014)` => PASS
    - `activate(neuro_unit_app)` => PASS
    - `query apps` => PASS (`neuro_unit_app` running)
    - post-activate `query device` => PASS
- Open risks:
  - failed `prepare` attempts still leave a truncated `/SD:/apps/neuro_unit_app.llext` artifact behind until the next successful overwrite; cleanup/rollback semantics can be hardened separately
  - the reconnect-monitor path remains only partially exercised in failure conditions after this fix because the main blocker was prepare-path session coupling, not a pure reconnect bug
- Rollback notes:
  - if dedicated artifact sessions prove too expensive, alternative designs would need an explicit async job/result protocol rather than reusing query handles across threads
- Next action:
  - document the prepare-plane split as the stable pattern for future artifact-driven operations and optionally harden failed-prepare cleanup of zero/truncated artifacts

### 2026-04-11

#### EXEC-038 Unit Generic Storage/Network Ops Foundation (Release-1.0.1 Bootstrap)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_shell.c`
  - `applocation/NeuroLink/neuro_unit/src/port/board_dnesp32s3b.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - introduced generic command-plane semantics in runtime command ABI: `storage_mount/storage_unmount/network_connect/artifact_fetch`
  - kept legacy aliases (`mount_sd/unmount_sd/wifi_connect/download`) for backward compatibility so existing board workflows and scripts do not break
  - upgraded command dispatch fallback policy so new generic ops can reuse legacy board hooks during migration
  - updated board provider wiring to expose both generic and legacy ops, enabling incremental board-port migration
  - switched Unit internal update/recovery paths to generic command IDs where storage mount and artifact fetch are required
  - added shell-level generic command aliases (`mount_storage`, `unmount_storage`, `network_connect`, `artifact_fetch`) while retaining legacy commands
- UT added or updated:
  - no new source-level UT landed in this slice; compatibility-first interface migration validated by build/link evidence
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit`
  - `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_app_command`
  - both commands linked successfully after generic ops bootstrap changes
- Open risks:
  - framework still contains direct Zephyr filesystem traversal in shell `ls`; next slice should route directory listing through storage ops contract to reduce FS coupling
  - `dnesp32s3b` provider currently maps generic ops to SD/WiFi implementations; additional non-SD or non-WiFi providers are still pending
- Rollback notes:
  - if compatibility issues are observed, fallback is to keep new generic symbols but route shell and internal call sites back to legacy aliases without removing ABI additions
- Next action:
  - close remaining `release-1.0.0` blockers (`R1-BLK-001/002/003`) in parallel with `release-1.0.1` board-port abstraction slices, without expanding 1.0.0 scope

#### EXEC-039 Storage Ops Contract Completion

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/src/port/board_dnesp32s3b.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - added `seed_path` field to `app_runtime_cmd_config` so recovery seed persistence path is now board-provider-configurable instead of hardcoded in the framework
  - changed framework-level fallback defaults: `APP_RT_DEFAULT_APPS_DIR` from `/SD:/apps` to `/apps`, added `APP_RT_DEFAULT_SEED_PATH "/recovery.seed"` so the framework layer carries no SD-specific path assumptions
  - propagated `seed_path` through `app_runtime_cmd_fill_defaults()` and the `app_runtime_cmd_get_config()` initialization guard
  - refactored `build_app_path()` in `neuro_unit.c` to derive the app artifact path from `app_runtime_cmd_get_config()->apps_dir` instead of the removed `NEURO_APP_PATH_FMT "/SD:/apps/%s.llext"` macro
  - updated `neuro_unit_start()` to derive the recovery seed store path from `cfg->seed_path`, retaining `NEURO_RECOVERY_SEED_PATH_DEFAULT` as a fallback guard
  - wired `dnesp32s3b` board provider to set explicit `apps_dir = "/SD:/apps"` and `seed_path = "/SD:/recovery.seed"` so current device behavior is preserved with no on-device behavior change
- UT added or updated:
  - no new source-level UT in this slice; storage abstraction validated by build/link evidence
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit` => linked successfully
  - `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_app_command` => all 264 build steps completed, `zephyr.elf` linked successfully
- Open risks:
  - `NEURO_RECOVERY_SEED_PATH_DEFAULT` and `NEURO_RECOVERY_SEED_PATH_LEGACY` constants in `neuro_recovery_seed_store.h` remain SD-specific for documentation purposes; they are no longer used directly in framework code but reflect the dnesp32s3b board convention
  - board providers that do not supply `seed_path` will fall back to the generic `/recovery.seed` default, which requires a mounted FS root with write access — adequate documentation in provider onboarding checklist (EXEC-041)
- Rollback notes:
  - if a board provider regression appears, restore `NEURO_APP_PATH_FMT` macro usage in `build_app_path()` and hard-code the seed path in `neuro_unit_start()` while retaining the `seed_path` ABI addition in the config struct
- Next action:
  - implement EXEC-040 Network Ops Contract Completion to extend the same generic abstraction to network connect and artifact fetch naming

#### EXEC-040 Design/Feature Drift Sync for 1.0.1 Baseline

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/UNIT_LLD.md`
  - `applocation/NeuroLink/AI_CORE_LLD.md`
  - `applocation/NeuroLink/CORE_CLI_CONTRACT.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `CORE-LLD-ARCH-*`
- Implementation summary:
  - synchronized Unit design with implemented update/artifact/recovery modules by adding explicit contract section and recovery snapshot structure so design anchors reflect shipped runtime behavior
  - reconciled AI Core design semantics for source-agent defaults by formalizing context-dependent policy (`affective` for interactive user path, `rational` allowed for operator/automation CLI path)
  - added Core CLI capability-to-resource-to-LLD traceability matrix and parity governance rules to reduce command drift risk during ongoing release-1.0.1 enhancement work
  - kept this slice documentation-only to avoid mixing behavior changes with design governance alignment
- UT added or updated:
  - `UT pending`; no source-level test delta in this design synchronization slice
- Verification evidence:
  - reviewed and updated design anchors to match implemented modules already present in runtime baseline: `neuro_update_manager`, `neuro_artifact_store`, `neuro_recovery_seed_store`
  - validated CLI contract now includes command/capability/LLD mapping and deferred placeholder governance
  - confirmed execution ledger append-only update completed with required traceability fields
- Open risks:
  - documentation now reflects current behavior, but runtime parity still depends on pending execution slices `EXEC-041` and `EXEC-042` for provider expansion and test matrix closure
  - `LLD.md` remains transitional and still contains residual normative content that should be converged in a later cleanup slice
- Rollback notes:
  - rollback is documentation-only and can be performed by reverting this entry and the paired design edits without affecting runtime binaries
- Next action:
  - continue with implementation slice `EXEC-041` to land board-provider expansion and compatibility validation under the refreshed design baseline

#### EXEC-041 Board Provider Expansion and Compatibility Validation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/neuro_unit/include/port/neuro_unit_port.h`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - added a generic fallback provider (`neuro_unit_port_provider_generic`) to establish a reusable integration pattern for non-`dnesp32s3b` board ports
  - changed port provider selection from fixed binding to board-aware selection logic in `neuro_unit_port_select_provider()` with deterministic fallback to `generic`
  - wired generic provider source into build graph and exported provider factory declaration through public port header
  - added a provider onboarding checklist in `neuro_unit/README.md` defining the required implementation and validation steps for future provider additions
- UT added or updated:
  - `UT pending`; no new source-level UT landed in this slice, compatibility validated via board and UT-target build/link evidence
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit` => linked successfully after provider selection + generic fallback integration
  - `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_app_command` => target linked successfully with all build steps completed
- Open risks:
  - new `generic` provider currently exposes no storage/network feature ops by design; non-`dnesp32s3b` boards still require provider-specific operation implementations before runtime parity can be claimed
  - provider selection currently matches board identity by string pattern; if board naming conventions diverge, selection mapping must be updated to avoid unintended fallback
- Rollback notes:
  - if selection logic causes board bring-up regressions, rollback to fixed `dnesp32s3b` binding in `neuro_unit_port_select_provider()` while retaining generic provider source as dormant template
- Next action:
  - execute `EXEC-042` test-matrix extension and evidence consolidation for missing-capability and mixed-medium scenarios

#### EXEC-042 Test Matrix Extension and Evidence Consolidation for 1.0.1

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - extended Unit UT matrix with a dedicated `app_runtime_cmd` capability-gate suite to validate missing-capability contract behavior under generic provider semantics
  - added focused UT cases for deterministic unsupported-path behavior (`NOT_SUPPORTED`), argument guardrails on supported generic operations, and legacy-hook to generic-op compatibility mapping
  - wired runtime command and exception modules into the app_command UT target for direct module-level validation and added port include path/source coverage required by new tests
  - updated UT testing guide to include the new module scope, case matrix, and revised total test-case count
- UT added or updated:
  - added `test_app_runtime_cmd_capability.c` with:
    - `test_generic_provider_reports_unsupported_ops`
    - `test_supported_op_requires_arguments`
    - `test_legacy_hooks_map_to_generic_ops`
  - updated `TESTING.md` matrix and total case count from `64` to `67`
- Verification evidence:
  - `conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_app_command` => linked successfully after new UT integration
  - `conda activate zephyr; west build -d build_neurolink_unit_ut_app_command` => incremental rebuild linked successfully after ztest fixture-signature cleanup
- Open risks:
  - this slice adds compile/link confidence and module-level assertions, but final simulator runtime pass/fail evidence remains pending in Linux environment per existing release decision
  - mixed-medium behavior across real alternative providers still requires follow-on provider-specific implementation and integration validation
- Rollback notes:
  - if new UT integration causes CI instability, rollback can remove `test_app_runtime_cmd_capability.c` and associated CMake wiring without impacting production runtime logic
- Next action:
  - proceed with Linux runtime evidence capture path for UT execution closure and begin first non-`dnesp32s3b` provider implementation based on the onboarding checklist

#### EXEC-043 Legacy Ops Deprecation Warning Baseline (Phase 1 Start)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_shell.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - started two-phase legacy-op deprecation implementation without breaking runtime compatibility
  - kept legacy shell commands (`mount_sd`, `unmount_sd`, `wifi_connect`, `download`) active, but added explicit deprecation guidance that points operators to generic commands (`mount_storage`, `unmount_storage`, `network_connect`, `artifact_fetch`)
  - validated that current migration boundary still includes legacy `demo_unit` runtime header constraints, so immediate source-level enum removal is deferred to the later cleanup phase
- UT added or updated:
  - `UT pending`; no new source-level UT landed in this start slice
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit` => linked successfully after deprecation-warning shell updates
  - `conda activate zephyr; west build -d build_neurolink_demo_unit` => linked successfully, confirming compatibility is preserved for legacy baseline paths
- Open risks:
  - deprecation warnings are currently shell-visible guidance; they do not yet enforce migration deadlines at compile time
  - full legacy alias removal still depends on downstream script/runbook migration and alignment of legacy runtime headers in non-`neuro_unit` baselines
- Rollback notes:
  - if warning verbosity impacts operator workflows, rollback can keep command aliases and move deprecation messaging from runtime shell output to documentation-only guidance
- Next action:
  - migrate operational runbooks and hardware SOP examples to generic command names, then add UT assertions for legacy-alias parity plus deprecation-path coverage before phase-2 alias removal

#### EXEC-044 Generic Ops Documentation and SOP Migration (Phase 1 Continuation)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/DEMO_RUNBOOK.md`
  - `applocation/NeuroLink/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - migrated operator-facing runbook command examples from legacy naming to generic naming (`mount_storage`, `network_connect`) as the default path
  - updated hardware retest SOP sections used for next execution to prioritize generic commands, while preserving explicit legacy alias compatibility notes
  - updated UT testing evidence wording to reflect generic-command-first guidance with legacy alias compatibility retained
  - intentionally preserved historical evidence records of previously executed legacy commands to avoid rewriting past test facts
- UT added or updated:
  - `UT pending`; no new source-level test cases landed in this documentation/SOP migration slice
- Verification evidence:
  - `DEMO_RUNBOOK.md` now presents generic ops as primary shell command path for storage/network bring-up
  - `HW_TEST_SESSION_2026-04-09.md` section `6.1`, section `8.2`, section `8.3`, and section `8.5` now prioritize generic command names for future replay steps
  - `neuro_unit/tests/app_command/TESTING.md` board-side prep evidence wording now reflects generic command naming and legacy alias support
- Open risks:
  - some historical log sections still contain legacy command strings by design (evidence preservation), which can be misread as current recommendation unless readers follow SOP sections
  - compile-time deprecation enforcement for legacy enums/fields is not yet introduced; current migration pressure remains runtime-shell/documentation guidance based
- Rollback notes:
  - this slice is documentation-only and can be reverted without binary impact if operator communication policy changes
- Next action:
  - add UT coverage for legacy-shell alias parity and deprecation-path expectations, then prepare phase-2 legacy alias removal gate checklist

#### EXEC-045 Phase-2 Legacy Alias Removal Gate Checklist Baseline

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - defined a formal pre-removal gate checklist for phase-2 legacy alias cleanup so alias deletion is tied to measurable readiness criteria instead of ad-hoc timing
  - aligned gate conditions with current migration reality: documentation path is generic-first, legacy shell aliases remain runtime-compatible, and legacy runtime headers still exist in compatibility baselines
  - established explicit rollback and defer behavior if any gate remains open
- UT added or updated:
  - `UT pending`; this slice adds governance checklist only
- Verification evidence:
  - added section `8.4 Legacy Alias Phase-2 Removal Gate Checklist` with checklist items, pass criteria, and execution command anchors
  - checklist requires both source-level and operator-level migration completion before removing aliases from runtime ABI and shell registration
- Open risks:
  - if checklist is treated as advisory rather than mandatory, phase-2 alias removal can still cause downstream script or board SOP breakage
  - `demo_unit` legacy-header convergence remains an explicit dependency before source-level enum alias deletion
- Rollback notes:
  - documentation-only baseline; rollback can remove section `8.4` and this log entry without runtime binary changes
- Next action:
  - execute remaining gate items (UT parity, downstream grep-zero checks, legacy-header convergence), then open a dedicated phase-2 code cleanup slice

#### EXEC-046 Legacy Alias UT Parity and Gate Evidence Scan

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - expanded `app_runtime_cmd` capability UT with explicit legacy/generic enum parity assertions and reverse-path execution coverage
  - added test to assert legacy enum IDs and generic enum IDs remain value-equivalent for compatibility window guarantees
  - added test to assert legacy enum execution still works when only generic hooks are wired, complementing existing generic-to-legacy hook mapping case
  - executed gate-evidence scan for legacy enum references and confirmed current source-level non-test usage is isolated to `demo_unit` compatibility path
  - confirmed header convergence blocker remains: `applocation/app_runtime_llext/include/app_runtime_cmd.h` is legacy-only and does not expose generic ids/fields used by `neuro_unit`
- UT added or updated:
  - added `test_legacy_enum_values_match_generic_ids`
  - added `test_generic_hooks_accept_legacy_enum_exec`
  - total UT case count updated from `67` to `69`
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit_ut_app_command` => linked successfully after new UT cases
  - source scan (`*.c`/`*.h`) shows legacy enum command IDs in active non-test code remain in:
    - `applocation/NeuroLink/demo_unit/src/neuro_demo.c`
    - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h` (alias definitions)
  - header diff evidence:
    - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h` includes generic ids (`APP_RT_CMD_STORAGE_MOUNT`, `APP_RT_CMD_NETWORK_CONNECT`, etc.) and compatibility aliases
    - `applocation/app_runtime_llext/include/app_runtime_cmd.h` remains legacy-only (`APP_RT_CMD_MOUNT_SD`, `APP_RT_CMD_WIFI_CONNECT`, etc.)
- Open risks:
  - gate `GATE-LGCY-004` (header convergence) remains open until `app_runtime_llext` baseline is converged or retired
  - gate `GATE-LGCY-001` cannot close while `demo_unit/src/neuro_demo.c` still depends on legacy enum ids by source name
- Rollback notes:
  - if new UT assertions cause integration friction, rollback can remove only the two new cases while preserving existing compatibility coverage
- Next action:
  - plan a dedicated header-convergence slice for `app_runtime_llext` vs `neuro_unit` command ABI, then migrate `demo_unit` enum callsites to generic names and re-run gate scan

#### EXEC-047 Legacy Header Convergence and Deferred-Slice Traceability Sync

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/app_runtime_llext/include/app_runtime_cmd.h`
  - `applocation/app_runtime_llext/src/app_runtime_cmd.c`
  - `applocation/app_runtime_llext/src/board_dnesp32s3b.c`
  - `applocation/NeuroLink/demo_unit/src/neuro_demo.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - completed `app_runtime_llext` command ABI convergence to generic-first IDs (`storage_mount/storage_unmount/network_connect/artifact_fetch`) while retaining legacy enum aliases for compatibility window stability
  - expanded `app_runtime_llext` command support/ops/config structures with generic fields and `seed_path`, and aligned dispatcher/fallback behavior to honor generic and legacy hooks consistently
  - updated `app_runtime_llext` board provider wiring to register both generic and legacy feature hooks to the same SD/Wi-Fi implementations, preserving existing board behavior
  - migrated active `demo_unit` prepare-path command callsites from legacy enum names to generic enum names to reduce `GATE-LGCY-001` source-name dependency surface
  - expanded Unit capability UT with explicit precedence coverage when both generic and legacy hooks are present
  - formalized deferred traceability for `EXEC-024` and `EXEC-025` in this release stage: they remain post-`release-1.0.0` hardening slices unless release owner reclassifies them under section `6.3`
- UT added or updated:
  - added `test_generic_hooks_take_precedence_when_both_present`
  - updated app_command UT suite total case count from `69` to `70`
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit` => linked successfully
  - `conda activate zephyr; west build -d build_neurolink_demo_unit` => linked successfully after `demo_unit` generic enum callsite migration
  - `conda activate zephyr; west build -d build_neurolink_unit_ut_app_command` => linked successfully after UT expansion
  - source scan (`*.c`/`*.h`) for `APP_RT_CMD_(MOUNT_SD|UNMOUNT_SD|WIFI_CONNECT|DOWNLOAD)` in `applocation/NeuroLink` now reports matches only in explicit compatibility aliases/tests
- Open risks:
  - `R1-BLK-001` remains open because executable host runtime UT evidence is still Linux-environment pending; this slice intentionally stayed on Windows compile/link evidence path
  - header convergence was completed for `app_runtime_llext`, but phase-2 legacy alias removal remains gated by full compatibility-policy closure and explicit rollback readiness
- Rollback notes:
  - rollback can restore legacy-only fields/dispatch names in `app_runtime_llext` while retaining generic aliases in `neuro_unit` if downstream compatibility issues are discovered
  - `demo_unit` callsite rollback is one-slice reversible by switching enum names back without changing command execution behavior
- Next action:
  - run updated `GATE-LGCY-001/003/004/005` closure review and decide whether phase-2 alias removal is `ready` or remains `blocked`

#### EXEC-052 Rollback Checkpoint-First Recovery Window Hardening

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/neuro_update_manager.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_update_manager.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_update_manager.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - hardened rollback lifecycle with explicit two-stage transition: `ROLLBACK_PENDING -> ROLLING_BACK`, instead of collapsing both states at begin-time
  - added new update-manager API `neuro_update_manager_rollback_mark_in_progress()` so runtime enters destructive rollback operations only after checkpoint persistence succeeds
  - changed Unit rollback handler to persist recovery seed immediately after `rollback_begin` and before unload/restore operations, closing the power-loss window where rollback intent was in-memory only
  - added deterministic checkpoint-save failure handling path: if early seed persist fails, rollback transitions to `FAILED`, emits rollback error event, and returns `500` without entering unload flow
- UT added or updated:
  - updated rollback success/failure tests to assert new pending/in-progress transition
  - added `test_rollback_pending_can_fail_before_unload` to validate pending-stage failure semantics
  - UT total case count increased from `70` to `71`
- Verification evidence:
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m west build -p always -b qemu_x86 applocation/NeuroLink/neuro_unit/tests/app_command -d build_neurolink_unit_ut_qemu_x86` => PASS (`zephyr.elf` linked)
  - board-target build attempts are currently blocked in this host session by missing `esptool>=5.0.2` in PATH during CMake configure, so this slice is verified by host compile/link evidence only
- Open risks:
  - end-to-end board evidence for the new rollback checkpoint-failure branch is still pending because current board build path requires host `esptool` environment correction
  - runtime failure injection for actual power-cut between `ROLLBACK_PENDING` checkpoint and rollback completion is still an on-device follow-up item
- Rollback notes:
  - if compatibility regressions appear, fallback is to keep checkpoint-first save call while temporarily collapsing rollback states back to single-stage `ROLLING_BACK`
- Next action:
  - run on-device rollback fault-injection scenario to capture `ROLLBACK_PENDING` persistence and reboot reconcile behavior with real storage media

#### EXEC-053 On-Device Rollback Checkpoint-First Validation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/docs/integration/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - completed hardware replay for rollback path after `EXEC-052` two-stage state-machine hardening (`ROLLBACK_PENDING -> ROLLING_BACK`)
  - validated end-to-end sequence on real board: `query -> lease(activate) -> prepare -> verify -> activate -> lease(rollback) -> rollback -> query apps`
  - confirmed rollback path returns deterministic success reply and app state is recoverable through stable reference restoration
  - verified build/flash path is healthy again in this host setup after resolving prior environment/cache collisions (`build_neurolink_unit` canonical directory + env Scripts path)
- UT added or updated:
  - no new source-level UT in this slice; evidence is hardware execution replay
- Verification evidence:
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m west flash -d build_neurolink_unit --esp-device COM4` => PASS
  - serial monitor shows:
    - `NeuroLink zenoh queryables ready on node 'unit-01'`
    - rollback ingress log: `update query: neuro/unit-01/update/app/neuro_unit_app/rollback ...`
    - post-rollback query ingress: `state query: neuro/unit-01/query/apps`
  - Core CLI replies:
    - `deploy activate ...` => `status=ok`
    - `deploy rollback ... --reason checkpoint_probe_exec052` => `status=ok`
    - `query apps` => `neuro_unit_app` still `RUNNING` (stable restore semantics)
- Open risks:
  - this slice validates rollback happy-path and control-plane continuity, but has not yet injected a physical power cut inside the pending window
  - failure-branch evidence for `rollback checkpoint save failed` remains unobserved on real media and still requires explicit fault injection plan
- Rollback notes:
  - evidence-only slice; no runtime code changes were made
- Next action:
  - execute controlled power-cut injection between rollback begin checkpoint and completion, then verify reboot reconcile transitions and persisted state outcome

## 5. Next Planned Execution Slices

1. `EXEC-024`
  - on-device recovery-seed fault-injection validation for temp-write/rename/backup rollback windows and evidence capture.
  - status note: deferred by default as post-`release-1.0.0` hardening per section `6.4`; pull-in requires section `6.3` admission decision.
2. `EXEC-025`
  - recovery-seed schema migration table and first forward-compatibility skeleton (`v2` handler placeholder + migration UT scaffolding).
  - status note: deferred by default as post-`release-1.0.0` hardening per section `6.4`; pull-in requires section `6.3` admission decision.

## 6. Unit Release Boundary Freeze (`release-1.0.0`)

This section is the formal scope freeze for Unit `release-1.0.0`.

From this point onward, Unit work must follow this boundary and must not add new feature scope without version escalation.

### 6.1 In-Scope for `release-1.0.0`

1. Unit four-plane runtime baseline is complete and maintained:
  - `cmd / query / event / update`
2. Unit governed app command + callback bridge remains within current contract.
3. Update baseline includes:
  - `prepare -> verify -> activate -> rollback`
4. Recovery seed persistence + boot reconcile remains in `v1` compatibility window.
5. Lease-protected write operations and request metadata policy enforcement remain mandatory.
6. `applocation/NeuroLink/core_cli.py` is part of `release-1.0.0` scope and must align with Unit in-scope capabilities and governance rules.

### 6.2 Explicitly Out-of-Scope for `release-1.0.0` (Move to `release-1.1.0+`)

1. Any new communication plane, new external protocol, or gateway/federation expansion beyond current Unit baseline.
2. Recovery seed schema `v2+` migration framework or multi-version conversion rollout.
3. New app exposure model redesign (beyond current command/callback governance contract).
4. Non-critical observability refactors that do not change release safety/correctness.
5. `core_cli` independent feature expansion that is not required by Unit `release-1.0.0` in-scope functionality.

### 6.3 Change Admission Rule (Mandatory)

New requirements are allowed only if they satisfy at least one condition:

1. production defect fix (correctness/safety/security)
2. board bring-up blocker required for `release-1.0.0` shipment
3. compliance requirement explicitly mandated by release owner

Any request outside these conditions must be recorded as backlog for `release-1.1.0+` and must not be inserted into current release slices.

### 6.4 Planned Slice Reclassification

1. `EXEC-024` and `EXEC-025` are reclassified as post-`release-1.0.0` hardening work by default.
2. They may only be pulled into `release-1.0.0` if release owner marks them as shipment blockers under rule 6.3.

## 7. Unit Release 1.0.0 Completion Plan (Execution Baseline)

Date baseline: `2026-04-09`

### 7.1 Current Unit Completion Snapshot

1. Unit runtime baseline is implemented on `neuro_unit` for four planes:
  - `cmd / query / event / update`
2. Key governance modules are implemented and integrated:
  - request envelope + policy, lease manager, update manager, artifact store, recovery seed store, app command registry, callback bridge
3. Unit UT source matrix is implemented with 70 ztest cases under:
  - `applocation/NeuroLink/neuro_unit/tests/app_command`
4. Board-target build validation is green for Unit app and UT app targets.
5. Host runtime UT evidence remains missing on current Windows host because Twister discovers scenario but selects `0 configurations` for `native_sim`.

### 7.2 Release 1.0.0 Remaining Blockers (Unit)

1. `R1-BLK-001` (resumed by owner direction): Produce executable runtime pass/fail evidence for Unit UT suite (not only compile/link).
2. `R1-BLK-002`: Close release acceptance evidence bundle (command traces, build artifacts, UT report, risk waivers).
3. `R1-BLK-003`: Verify Core CLI to Unit capability parity against frozen 1.0.0 scope and reject non-scope command drift.

### 7.3 Planned Execution Slices for Release Close

1. `EXEC-028` Unit UT Runtime Evidence Path Unblock
  - Objective: establish at least one runnable host or board execution path with deterministic pass/fail output for the 70-case UT suite.
  - In-scope tasks:
    - validate Twister/platform mapping on current toolchain
    - if host path is still blocked, define board-side UT execution fallback with log capture contract
    - lock CI command contract for repeatable UT execution evidence
  - Exit criteria:
    - one reproducible command produces executable test run and result summary
    - result artifact path and command are documented in `TESTING.md`

2. `EXEC-029` Unit Release Evidence Consolidation
  - Objective: consolidate release evidence for 1.0.0 sign-off.
  - In-scope tasks:
    - collect `west build` evidence for `neuro_unit` and UT app
    - collect UT runtime report from `EXEC-028`
    - record unresolved known limitations with explicit waiver owner
  - Exit criteria:
    - single release evidence section in this ledger references exact commands, outputs, and artifact locations

3. `EXEC-030` Core CLI Parity and Admission-Gate Compliance Check
  - Objective: ensure `core_cli.py` is aligned with Unit release boundary and no out-of-scope commands enter 1.0.0.
  - In-scope tasks:
    - map CLI command set to Unit in-scope resources and policies
    - verify protected-write metadata requirements are enforced consistently
    - reject or defer non-1.0.0 additions under rule 6.3
  - Exit criteria:
    - command-to-capability matrix is complete and checked in
    - no unapproved command drift remains for release target `1.0.0`

4. `EXEC-031` Unit Release Candidate Freeze and Tag-Ready Review
  - Objective: complete final gate review before version tag.
  - In-scope tasks:
    - re-run required build and UT evidence commands
    - verify no open `release-1.0.0` blockers remain
    - mark post-release backlog transfer items explicitly
  - Exit criteria:
    - all `R1-BLK-*` items closed or waived by release owner
    - release candidate marked tag-ready in this ledger

### 7.4 Release 1.0.0 Done Criteria (Unit)

1. Unit runtime builds clean on release board target and produces expected artifacts.
2. Unit UT suite has executable pass/fail evidence (not discovery-only).
3. Core CLI release target is aligned with Unit scope and admission rules.
4. All non-blocking enhancements are deferred to `release-1.1.0+` backlog.
5. Release evidence and residual risks are explicitly recorded with owners.

## 8. Unit Release 1.0.1 Enhancement Plan (Hardware Interface Generalization)

Date baseline: `2026-04-11`

### 8.1 Goal

1. Remove framework-level hard assumptions that Unit storage is SD and network is WiFi.
2. Make framework depend on generic storage/network capabilities and Ops contracts.
3. Keep concrete hardware implementation in board port providers.

### 8.2 Scope

In-scope:
1. runtime command ABI generalization (`storage_*`, `network_*`, `artifact_*` semantics)
2. storage/network capability probing and unsupported-path deterministic error contract
3. board-port provider Ops implementation for at least one non-SD or non-WiFi path
4. migration compatibility layer for existing `dnesp32s3b` SD/WiFi implementation

Out-of-scope:
1. new communication planes or gateway expansion
2. release-1.0.0 scope expansion outside blocker closure

### 8.3 Planned Execution Slices (Release-1.0.1)

1. `EXEC-039` Storage Ops Contract Completion
  - objective: finalize generic storage ops contract and remove direct framework dependence on SD-specific semantics
  - tasks:
    - add storage abstraction path for framework file operations
    - route shell `ls` and update artifact path checks through storage contract
    - ensure deterministic `-ENOTSUP` behavior when storage capability is absent
  - exit criteria:
    - framework paths compile without requiring SD-specific operation names

2. `EXEC-040` Design/Feature Drift Sync for 1.0.1 Baseline
  - objective: synchronize Design with implemented runtime/CLI feature set and eliminate known design drift
  - tasks:
    - align Unit update/artifact/recovery design anchors with implemented modules
    - align Core source-agent policy semantics with CLI operational defaults
    - add CLI capability-to-LLD traceability matrix
  - exit criteria:
    - Design and contract docs reflect current implementation and governance baseline

3. `EXEC-041` Board Provider Expansion and Compatibility Validation
  - objective: prove board-port extensibility with at least one provider variation and no dnesp32s3b regression
  - tasks:
    - add provider integration pattern for alternative storage or network medium
    - run compatibility build/regression for existing dnesp32s3b provider
    - document provider onboarding checklist
  - exit criteria:
    - provider Ops model validated and existing board behavior remains stable

4. `EXEC-042` Test Matrix and Release Evidence for 1.0.1 Enhancement
  - objective: close evidence loop for generic hardware abstraction behavior
  - tasks:
    - add/extend UT and integration matrix for missing capability and mixed-medium scenarios
    - capture build and execution evidence for generalized interfaces
    - record residual risks and waivers if needed
  - exit criteria:
    - enhancement evidence package is complete and traceable in this ledger

### 8.4 Legacy Alias Phase-2 Removal Gate Checklist

Phase-2 alias removal (`mount_sd`/`wifi_connect`/`download` and related enum/field aliases) may start only when all items below are closed.

1. Source callsite gate (`GATE-LGCY-001`)
  - `neuro_unit` and compatibility baselines (`demo_unit` included) have no active source callsites depending on legacy enum IDs by name.
  - verification command anchor:
    - `rg "APP_RT_CMD_(MOUNT_SD|UNMOUNT_SD|WIFI_CONNECT|DOWNLOAD)" applocation/NeuroLink`
  - pass criteria:
    - no matches outside explicit compatibility shims planned for same removal slice.

2. Operator/SOP gate (`GATE-LGCY-002`)
  - runbooks and active SOP sections use generic commands as the primary path.
  - verification anchor:
    - `DEMO_RUNBOOK.md` and `HW_TEST_SESSION_2026-04-09.md` future-execution sections show `mount_storage`/`network_connect`/`artifact_fetch` first.
  - pass criteria:
    - legacy names appear only in compatibility notes or historical evidence blocks.

3. UT parity gate (`GATE-LGCY-003`)
  - UT must assert both behaviors during transition window:
    - generic command path passes
    - legacy alias path passes with deprecation guidance visible
  - verification command anchor:
    - `west build -d build_neurolink_unit_ut_app_command`
  - pass criteria:
    - UT source includes explicit alias-parity and deprecation-path coverage and target links successfully.

4. Header convergence gate (`GATE-LGCY-004`)
  - compatibility headers consumed by non-`neuro_unit` baselines expose required generic command IDs/fields or are retired.
  - pass criteria:
    - no target fails solely because generic IDs are missing from legacy runtime headers.

5. Build regression gate (`GATE-LGCY-005`)
  - removal candidate branch must validate key targets before merge.
  - verification command anchors:
    - `west build -d build_neurolink_unit`
    - `west build -d build_neurolink_demo_unit`
  - pass criteria:
    - both targets link successfully or documented deprecation policy explicitly retires the target in same change set.

6. Rollback readiness gate (`GATE-LGCY-006`)
  - rollback path is documented before alias deletion.
  - pass criteria:
    - a one-slice rollback can restore alias fields/registration without touching unrelated runtime behavior.

If any gate is open, phase-2 alias removal is deferred and tracked as `blocked` until closure evidence is appended in this ledger.

### 2026-04-11

#### EXEC-048 Legacy Alias Phase-2 Implementation and demo_unit Retirement

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_shell.c`
  - `applocation/NeuroLink/neuro_unit/src/port/board_dnesp32s3b.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/CORE_DEMO.md`
  - `applocation/NeuroLink/DEMO_RUNBOOK.md`
  - `applocation/NeuroLink/demo_unit/*` (removed)
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - removed legacy command enum aliases (`APP_RT_CMD_MOUNT_SD`, `APP_RT_CMD_UNMOUNT_SD`, `APP_RT_CMD_WIFI_CONNECT`, `APP_RT_CMD_DOWNLOAD`) from Unit runtime command ABI
  - removed legacy capability fields and legacy operation hooks from `app_runtime_cmd` config structs and removed compatibility fallback fill path
  - switched runtime shell to generic-only active command surface (`mount_storage`, `unmount_storage`, `network_connect`, `artifact_fetch`) and removed legacy alias command registrations
  - aligned board provider and generic provider command configuration to generic-only support/ops fields
  - updated capability UT to validate generic-only behavior and explicit generic hook registration requirements
  - removed `applocation/NeuroLink/demo_unit` project sources/configuration to make `neuro_unit` the only active Unit baseline
  - updated active runbook/core demo references to `neuro_unit` build/artifact paths
- UT added or updated:
  - updated `test_app_runtime_cmd_capability.c` to remove legacy-parity assertions and add generic-only not-supported checks
- Verification evidence:
  - `conda activate zephyr; west build -d build_neurolink_unit` => linked successfully
  - `conda activate zephyr; west build -d build_neurolink_unit_ut_app_command` => linked successfully
- Open risks:
  - Linux/WSL runtime execution evidence for UT remains pending and is still required for final executable pass/fail closure
  - historical docs may still reference `demo_unit` paths in archival sections; active runbook paths were updated in this slice
- Rollback notes:
  - rollback requires restoring removed `demo_unit` tree and reintroducing legacy aliases in `app_runtime_cmd` headers/runtime and shell command registration
- Next action:
  - run UT suite in Linux/WSL and append executable pass/fail evidence, then close release evidence gap

#### EXEC-049 Unit UT Linux Runtime Evidence Automation and Host Readiness Gate

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_from_windows.ps1`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - added a Linux one-command evidence script (`run_ut_linux.sh`) that captures Twister attempt log, qemu_x86_64 build log, qemu_x86_64 runtime log, and a result summary under timestamped evidence directory
  - added a Windows-trigger helper (`run_ut_from_windows.ps1`) so prepared WSL environments can execute the same Linux evidence flow from PowerShell with deterministic entry command
  - updated UT testing guide to reflect current generic-only `app_runtime_cmd` capability tests and documented the scripted runtime-evidence path and local readiness checks
  - corrected stale Unit release snapshot text from `64` to `70` test cases for consistency with current UT suite
- UT added or updated:
  - no new ztest source cases in this slice; evidence automation and documentation alignment only
- Verification evidence:
  - `wsl -l -v` => host reports no installed WSL distribution
  - `wsl --list --online` => timed out in current network context (`Wsl/WININET_E_TIMEOUT`)
  - `pwsh -File applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_from_windows.ps1` => prints missing-distro guidance and exits with code `2`
  - `conda run -n zephyr west build -d build_neurolink_unit_ut_app_command` => linked successfully (host build path remains healthy)
- Open risks:
  - `R1-BLK-001` remains open until `run_ut_linux.sh` is executed on a Linux-capable node with `west` and `qemu-system-x86_64` available and pass/fail logs are appended
  - local Windows workstation still cannot provide executable runtime evidence because no runnable Linux/WSL chain is currently provisioned
- Rollback notes:
  - rollback can remove the two helper scripts and revert testing-guide command references without affecting runtime production binaries
- Next action:
  - run `run_ut_linux.sh` on Linux CI/runner, attach `summary.txt` + runtime logs to this ledger, then close `R1-BLK-001`

#### EXEC-050 NeuroLink Directory Normalization and Unit CLI Subproject Extraction

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` (moved)
  - `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` (moved)
  - `applocation/NeuroLink/subprojects/unit_cli/scripts/invoke_core_cli.py` (moved and path fixed)
  - `applocation/NeuroLink/subprojects/unit_cli/docs/*` (moved)
  - `applocation/NeuroLink/subprojects/unit_cli/skill/*` (moved)
  - `applocation/NeuroLink/docs/integration/*` (moved)
  - `applocation/NeuroLink/docs/project/*` (moved)
  - `applocation/NeuroLink/docs/archive/*` (moved)
  - `applocation/NeuroLink/core_cli.py` (compat wrapper)
  - `applocation/NeuroLink/tests/test_core_cli.py` (compat wrapper)
  - `applocation/NeuroLink/core_cli_skill/*` (compat pointers)
  - `applocation/NeuroLink/SMOKE_017B.ps1`
  - `applocation/NeuroLink/LLD.md`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `CORE-LLD-ARCH-*`
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - created module-oriented documentation root at `applocation/NeuroLink/docs` and migrated project, integration, and archive documents out of top-level scatter layout
  - extracted Unit CLI assets into canonical subproject path `applocation/NeuroLink/subprojects/unit_cli` with standardized `src/scripts/docs/tests/skill` layout
  - kept backward compatibility by adding wrapper/pointer files at legacy paths, so existing commands and references continue to work during transition
  - cleaned disposable artifacts (`twister-out*`, `*.bak`, `__pycache__`, stale smoke evidence) to reduce repository noise
- UT added or updated:
  - no new test logic; migrated test location and validated both canonical and compatibility test entrypoints
- Verification evidence:
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m unittest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` => PASS (11 tests)
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m unittest applocation/NeuroLink/tests/test_core_cli.py` => PASS (11 tests)
  - `D:/Compiler/anaconda/envs/zephyr/python.exe applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py --help` => PASS
  - `D:/Compiler/anaconda/envs/zephyr/python.exe applocation/NeuroLink/core_cli.py --help` => PASS
- Open risks:
  - historical progress entries still include legacy file paths; compatibility stubs prevent hard breaks but path references are not yet fully normalized
  - CI/build scripts outside NeuroLink may still point to legacy locations and need follow-up sweep
- Rollback notes:
  - rollback can restore pre-extraction layout by moving files back from `subprojects/unit_cli` and `docs/*`, then removing wrapper/pointer files
- Next action:
  - phase out compatibility stubs after CI and team scripts are updated to canonical paths

#### EXEC-051 Ordered Standardization Follow-up and Centralized Build Directory Policy

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/docs/integration/DEMO_RUNBOOK.md`
  - `applocation/NeuroLink/docs/integration/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/SMOKE_017B.ps1`
  - `applocation/NeuroLink/subprojects/unit_cli/docs/CORE_DEMO.md`
  - `applocation/NeuroLink/subprojects/unit_cli/docs/CORE_CLI_SKILLS_SCHEMA.md`
  - `applocation/NeuroLink/subprojects/unit_cli/skill/README.md`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh`
  - `applocation/NeuroLink/docs/project/DIRECTORY_GOVERNANCE.md`
  - `applocation/NeuroLink/docs/README.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - executed ordered follow-up actions: active-path normalization updates, build-output consolidation, and governance-rule codification
  - created centralized workspace build hierarchy at `build/<target>` and moved all root `build_*` output directories under `build/`
  - updated active NeuroLink docs/scripts to reference canonical Unit CLI entry and standardized build output paths
  - codified project directory/build governance in a dedicated policy document and linked it from docs index
- UT added or updated:
  - no new test logic; test documentation and Linux UT helper path updated to centralized build hierarchy
- Verification evidence:
  - root directory check after migration: only `build/` remains as build output root
  - subdirectory check confirms migrated outputs under `build/app_runtime_llext`, `build/network_demo`, `build/neurolink_unit`, and Unit UT target subdirectories
- Open risks:
  - historical ledger entries intentionally retain original command/evidence paths and are not retroactively rewritten
  - some archival docs still contain legacy path examples for historical replay context
- Rollback notes:
  - rollback can move directories from `build/<target>` back to legacy root `build_*` names and revert command references in active docs/scripts
- Next action:
  - remove remaining legacy path examples from non-archival docs after team confirms all automation uses canonical `build/<target>` and Unit CLI subproject entry

#### EXEC-054 Release-1.0.0 Blocker-First Implementation Kickoff (Linux UT CI Path + Parity Recheck)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `.github/workflows/neurolink_unit_ut_linux.yml`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - started `EXEC-054` as a blocker-first release slice under `release-1.0.0` governance, without introducing new runtime feature scope
  - added Linux CI workflow entrypoint to execute Unit UT runtime evidence script (`run_ut_linux.sh`) on `ubuntu-22.04` and publish evidence artifacts automatically
  - updated UT testing guide with CI-hosted Linux evidence path so `R1-BLK-001` can be closed via deterministic runner output even when local Windows host has no runnable WSL chain
  - aligned release closure path to use canonical build/evidence references and explicit artifact bundle requirements (`summary + raw logs`)
- UT added or updated:
  - no new ztest source case in this kickoff slice; test execution infrastructure and evidence procedure were expanded
- Verification evidence:
  - local verification commands executed in this slice:
    - `conda run -n zephyr west build -d build/neurolink_unit`
    - `conda run -n zephyr west build -d build/neurolink_unit_ut_app_command`
    - `D:/Compiler/anaconda/envs/zephyr/python.exe -m unittest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`
  - CI verification command path added:
    - GitHub Actions workflow `.github/workflows/neurolink_unit_ut_linux.yml` -> `bash applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh`
  - release-evidence artifact contract retained:
    - `applocation/NeuroLink/smoke-evidence/ut-runtime/<timestamp>/summary.txt`
    - `twister_native_sim.log`, `qemu_x86_64_build.log`, `qemu_x86_64_run.log`
- Open risks:
  - `R1-BLK-001` remains open until the newly added Linux CI path is executed at least once and attached logs demonstrate executable pass/fail output
  - release blocker closure is still evidence-gated; this kickoff slice prepares the path but does not itself constitute runtime execution proof
- Rollback notes:
  - rollback can remove `.github/workflows/neurolink_unit_ut_linux.yml` and revert the `TESTING.md` CI references without affecting runtime binaries
- Next action:
  - run the Linux CI workflow once, append artifact paths and result summary in this ledger, then move `R1-BLK-001` from open to closed (or blocked with explicit owner if runner environment fails)

#### EXEC-055 Windows Build/Test Terminal Policy Freeze (PowerShell + conda activate zephyr)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/docs/project/DIRECTORY_GOVERNANCE.md`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - established an explicit project policy on Windows hosts: all compile/test execution must run in PowerShell and must activate environment via `conda activate zephyr` before build/test commands
  - updated project governance document to mark cmd/bash and `conda run` as non-default for primary Windows build/test evidence paths
  - updated Unit UT testing guide command blocks to include the activation pre-step for reproducible operator execution
- UT added or updated:
  - no source-level UT changes; governance and procedure documentation only
- Verification evidence:
  - policy was added to governance rule set and UT execution procedure under canonical docs
  - active command snippets now include explicit activation sequence (`D:/Compiler/anaconda/Scripts/activate` then `conda activate zephyr`)
- Open risks:
  - existing historical entries and old ad-hoc logs may still show legacy command style (`conda run`) and are retained as historical evidence
  - strict compliance depends on operator/script adherence until all external automation callers are aligned
- Rollback notes:
  - if policy needs relaxation for exceptional CI contexts, rollback can revert only the mandatory wording while keeping command examples intact
- Next action:
  - enforce this policy in all subsequent execution slices and update any remaining active non-archival docs that still use non-PowerShell/non-activate command style

#### EXEC-056 PowerShell Activation Reliability and Local Evidence Re-validation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - revalidated local build/test evidence under mandatory Windows policy using PowerShell sessions and explicit `conda activate zephyr`
  - diagnosed activation fragility in non-initialized PowerShell sessions (`conda` resolves to `conda.bat`), then standardized hook pre-step to guarantee environment switch reliability before build/test commands
  - diagnosed UT build failure as stale dual-directory artifact conflict (`build/neurolink_unit_ut_app_command` vs `build_neurolink_unit_ut_app_command`), cleaned conflicting generated directories, and reran a clean canonical rebuild successfully
- UT added or updated:
  - no source-level UT case changes; procedure-level activation reliability note and command pre-steps were updated in UT testing guide
- Verification evidence:
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression ; conda activate zephyr ; west build -p always -b dnesp32s3b/esp32s3/procpu -s applocation/NeuroLink/neuro_unit -d build/neurolink_unit` => PASS
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression ; conda activate zephyr ; west build -p always -b dnesp32s3b/esp32s3/procpu -s applocation/NeuroLink/neuro_unit/tests/app_command -d build/neurolink_unit_ut_app_command` => PASS
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression ; conda activate zephyr ; D:/Compiler/anaconda/envs/zephyr/python.exe -m unittest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` => PASS (`Ran 11 tests ... OK`)
- Open risks:
  - `R1-BLK-001` remains open because Linux runtime execution evidence (`run_ut_linux.sh` artifact bundle) is still pending
  - current local evidence is compile/link + CLI UT only and does not replace Linux runnable UT pass/fail closure requirement
- Rollback notes:
  - rollback can revert hook pre-step guidance in `TESTING.md` if organization later enforces global `conda init powershell`; runtime binaries are unaffected
- Next action:
  - trigger `.github/workflows/neurolink_unit_ut_linux.yml`, collect `summary.txt` and runtime logs, then append closure evidence to move `R1-BLK-001` to closed

#### EXEC-057 Linux UT Runtime Validation Deferred (Pending Mark)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - deferred Linux-side Unit UT runtime validation in this phase based on owner direction
  - explicitly changed release blocker wording to mark `R1-BLK-001` as `pending` instead of active immediate execution
  - kept existing Linux evidence path (`run_ut_linux.sh` and CI workflow) intact for future resumption without additional rework
- UT added or updated:
  - no source-level UT changes in this slice
- Verification evidence:
  - documentation-only state transition in this ledger; no new Linux runtime execution command was run in this slice
- Open risks:
  - executable runtime UT evidence is still missing, so release closure cannot claim runnable host/simulator proof yet
  - pending duration must be actively tracked to avoid indefinite blocker drift
- Rollback notes:
  - rollback can revert `R1-BLK-001` wording from `pending` to active open execution requirement without touching runtime code
- Next action:
  - resume Linux UT runtime evidence execution when owner re-enables this track, then append logs and update blocker status from `pending` to `closed` or `blocked`

### 2026-04-12

#### EXEC-058 Linux UT Track Paused and Workstream Switch Confirmation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
- Implementation summary:
  - explicitly marked Linux-side UT runtime evidence track as `paused` for the current phase
  - confirmed workstream switch to non-Linux-UT tasks while preserving the existing Linux evidence scripts/workflow for later resume
  - kept release governance unchanged: pause status is a scheduling decision, not feature-scope expansion
- UT added or updated:
  - no source-level UT changes in this slice
- Verification evidence:
  - ledger status text updated: `R1-BLK-001` now explicitly states `paused by owner direction`
  - no new Linux runtime execution command was run in this slice
- Open risks:
  - runnable host/simulator UT pass/fail evidence is still missing until the paused track is resumed
  - release closure still requires owner decision on waiver/closure path for paused blocker items
- Rollback notes:
  - rollback can restore `R1-BLK-001` wording from `paused` to `pending` or active-open without touching runtime code
- Next action:
  - proceed with other approved release tasks under current scope gate; resume Linux UT track only when owner re-enables it

#### EXEC-059 Provider Selection Override for Generic Capability Validation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/Kconfig`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port.c`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - added new build-time config switch `CONFIG_NEURO_UNIT_PORT_FORCE_GENERIC` in `neuro_unit/Kconfig`
  - updated provider selection logic so the switch can force `generic` provider selection ahead of board-name matching
  - documented the override usage in runtime notes and provider onboarding checklist to support deterministic capability-gate validation slices
- UT added or updated:
  - no source-level UT changes in this slice; behavior is validated by build/link and existing capability-gate test path
- Verification evidence:
  - pending local build verification commands for `neuro_unit` and `neuro_unit/tests/app_command` in PowerShell + `conda activate zephyr` session
- Open risks:
  - the new override is build-time global; it should only be enabled in validation-oriented configs to avoid accidental production fallback to generic provider
  - no dedicated selector-unit-test case yet for forced-generic branch; current confidence relies on compile/link and runtime log visibility
- Rollback notes:
  - rollback can remove `CONFIG_NEURO_UNIT_PORT_FORCE_GENERIC` and the selector branch without affecting board-provider implementation bodies
- Next action:
  - run board build and UT-target build under default config, then optionally run one force-generic build profile to confirm deterministic provider override behavior

#### EXEC-060 Provider Override Verification Closure (PowerShell Policy)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - completed the pending local verification evidence for `EXEC-059` under the mandatory Windows execution policy (PowerShell plus explicit `conda activate zephyr`)
  - validated default provider path build/link for both Unit app target and Unit UT app target
  - validated forced provider override profile by compiling `neuro_unit` with `CONFIG_NEURO_UNIT_PORT_FORCE_GENERIC=y` and confirming final link/artifact generation
  - kept this slice verification-only with no runtime feature expansion
- UT added or updated:
  - no source-level UT changes in this slice
- Verification evidence:
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression ; conda activate zephyr ; west build -p always -b dnesp32s3b/esp32s3/procpu -s applocation/NeuroLink/neuro_unit -d build/neurolink_unit` => PASS (`build/neurolink_unit/zephyr/zephyr.elf` linked)
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression ; conda activate zephyr ; west build -p always -b dnesp32s3b/esp32s3/procpu -s applocation/NeuroLink/neuro_unit/tests/app_command -d build/neurolink_unit_ut_app_command` => PASS (`build/neurolink_unit_ut_app_command/zephyr/zephyr.elf` linked)
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression ; conda activate zephyr ; west build -p always -b dnesp32s3b/esp32s3/procpu -s applocation/NeuroLink/neuro_unit -d build/neurolink_unit_force_generic -- -DCONFIG_NEURO_UNIT_PORT_FORCE_GENERIC=y` => PASS (`build/neurolink_unit_force_generic/zephyr/zephyr.elf` linked)
- Open risks:
  - no dedicated selector-unit-test case exists yet for the forced-generic branch in provider selection; current confidence remains compile/link based for that specific branch
  - Linux executable UT runtime evidence track remains paused by owner direction, so this slice does not change `R1-BLK-001` status
- Rollback notes:
  - this is a ledger/evidence synchronization slice only; rollback impact is limited to documentation history
- Next action:
  - optionally open a focused UT slice to add direct selector branch coverage for `CONFIG_NEURO_UNIT_PORT_FORCE_GENERIC` and reduce compile/link-only confidence risk

#### EXEC-061 Linux UT Track Resume, WSL Ubuntu Provisioning, and Runtime Method Hardening

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_request_envelope.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_neuro_request_policy.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - resumed Linux UT runtime evidence track and switched blocker wording from paused to resumed under owner direction
  - fixed two runtime UT failure points observed on qemu run:
    - updated request-policy UT expectation so `rollback` is treated as protected-write action (aligned with shipped update contract)
    - restored deterministic metadata validation order in `neuro_request_envelope` so `priority` check precedes `idempotency_key` check
  - hardened Linux evidence script for operator visibility and stability:
    - auto-detect/export `ZEPHYR_SDK_INSTALL_DIR`
    - stream build/run logs in real time via `tee`
    - enforce configurable run timeout (`RUN_TIMEOUT_SEC`, default 900s)
    - emit explicit `qemu_build_rc` in `summary.txt`
  - documented WSL Ubuntu setup and runtime procedure for domestic-network operation, including mirror-first bootstrap and scripted trigger path from Windows
- UT added or updated:
  - updated `test_neuro_request_policy.c` rollback policy assertion to protected-write requirement
  - no new test case count increase in this slice; focused on failing-case alignment and runner method hardening
- Verification evidence:
  - local WSL Ubuntu readiness and SDK/toolchain installation completed:
    - `~/.local/bin/west sdk install -b /home/emb -t x86_64-zephyr-elf`
  - post-change Linux runtime script execution:
    - `pwsh applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_from_windows.ps1 -Distro Ubuntu`
    - evidence directory: `applocation/NeuroLink/smoke-evidence/ut-runtime/20260412T074758Z`
    - summary result shows script reached run stage with explicit RCs:
      - `twister_native_sim_rc=0`
      - `qemu_build_rc=0`
      - `qemu_run_rc=143` (run terminated externally in this attempt; further full-pass capture still required)
- Open risks:
  - qemu runtime still needs uninterrupted completion evidence in local WSL path to convert current execution from method validation to final pass/fail closure for blocker evidence
  - Twister `native_sim` on this workspace still reports scenario discovery with `0 configurations`, so qemu_x86_64 remains the practical executable path for now
- Rollback notes:
  - if runtime method hardening introduces workflow friction, rollback can keep SDK auto-detection and remove `tee/timeout` behavior while preserving UT-fix code alignment
- Next action:
  - perform one uninterrupted `run_ut_from_windows.ps1` execution to generate final `summary.txt` with complete qemu test termination semantics (success or deterministic failure without manual interruption)

### 2026-04-14

#### EXEC-062 Linux UT Runtime Evidence Closure and Runner Fix Finalization

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
- Implementation summary:
  - completed the pending `EXEC-061` follow-up and closed Linux UT runtime evidence loop with a fresh PASS artifact bundle
  - fixed qemu runtime execution path in UT runner from wrapped `west build -t run` to direct `ninja -C build/neurolink_unit_ut_qemu_x86_64_linux run_qemu`
  - added explicit `ninja` dependency check and strengthened pass/fail parsing to accept complete suite summary success while still rejecting fatal/fail signatures
  - fixed qemu log capture reliability by running via pseudo-terminal (`script -q -f -e`) so ztest output is preserved in file logs even when timeout terminates qemu after successful execution
- UT added or updated:
  - no new source-level ztest case in this slice
  - UT runtime execution method and evidence capture path were updated in runner script
- Verification evidence:
  - terminal execution sequence (PowerShell + `conda activate zephyr` policy):
    - `wsl -d Ubuntu bash -lc "cd /mnt/d/Software/project/zephyrproject && west build -d build/neurolink_unit_ut_qemu_x86_64_linux -t help | sed -n '/run/,+40p'"`
    - `wsl -d Ubuntu bash -lc "cd /mnt/d/Software/project/zephyrproject && timeout 120s ninja -C build/neurolink_unit_ut_qemu_x86_64_linux run_qemu"`
    - `pwsh applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_from_windows.ps1 -Distro Ubuntu -RunTimeoutSec 180`
    - `wsl -d Ubuntu bash -lc "cd /mnt/d/Software/project/zephyrproject && RUN_TIMEOUT_SEC=180 ./applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh"`
    - `wsl -d Ubuntu bash -lc "cd /mnt/d/Software/project/zephyrproject && RUN_TIMEOUT_SEC=120 ./applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh"`
  - intermediate evidence (before final fix) retained for traceability:
    - `applocation/NeuroLink/smoke-evidence/ut-runtime/20260413T165516Z/summary.txt` (`result=FAIL`, log-file-missing issue)
    - `applocation/NeuroLink/smoke-evidence/ut-runtime/20260413T170347Z/summary.txt` (`result=FAIL`, empty qemu log issue)
  - final closure evidence:
    - `applocation/NeuroLink/smoke-evidence/ut-runtime/20260413T171425Z/summary.txt`
      - `result=PASS`
      - `twister_native_sim_rc=0`
      - `qemu_build_rc=0`
      - `qemu_run_rc=124` (timeout termination after completed test summary)
    - `applocation/NeuroLink/smoke-evidence/ut-runtime/20260413T171425Z/qemu_x86_64_run.log`
      - contains full ztest execution including `TESTSUITE SUMMARY END`, all suites `SUITE PASS`, and `PROJECT EXECUTION SUCCESSFUL`
- Open risks:
  - Twister `native_sim` still shows `0 configurations` in this workspace, so runnable host-runtime evidence continues to rely on qemu_x86_64 path
  - qemu run is timeout-terminated by design in current method; result parsing now depends on summary/failure signature correctness and should be kept under review if Zephyr output format changes
- Rollback notes:
  - if future environment no longer requires pseudo-terminal capture, rollback can remove `script -q -f -e` path and keep direct run with unchanged parsing logic
  - if `ninja run_qemu` target behavior changes in upstream Zephyr, fallback is to reintroduce board-specific west runner invocation with explicit TTY-safe logging
- Next action:
  - optionally add one dedicated UT case for runner-result parsing contract in CI-side script tests to guard against log-format drift

#### EXEC-063 Release-1.0.1 Start: Ops Split and Zenoh Endpoint Configurability Baseline

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_shell.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic.c`
  - `applocation/NeuroLink/neuro_unit/src/port/board_dnesp32s3b.c`
  - `applocation/NeuroLink/neuro_unit/include/neuro_unit.h`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/Kconfig`
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/boards/dnesp32s3b_esp32s3_procpu.conf`
  - `applocation/NeuroLink/neuro_unit/src/main.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - split Unit hardware-related command abstraction from a single `feature_ops` block into two explicit groups: `storage_ops` and `network_ops`, and aligned support flags to `support.storage.*` plus `support.network.*`
  - updated runtime dispatcher and provider wiring (`generic` and `dnesp32s3b`) to the split contract without changing command-plane behavior (`storage_mount/storage_unmount/network_connect/artifact_fetch`)
  - removed hardcoded zenoh/node compile definitions from `CMakeLists.txt` and introduced Kconfig-backed defaults (`CONFIG_NEUROLINK_NODE_ID`, `CONFIG_NEUROLINK_ZENOH_MODE`, `CONFIG_NEUROLINK_ZENOH_CONNECT`)
  - added runtime zenoh endpoint override control surface (`app zenoh_connect_show|set|clear`) with reconnect-on-change behavior, using priority `runtime override > Kconfig default`
- UT added or updated:
  - updated `test_app_runtime_cmd_capability.c` to use split support/ops structure (`network_ops` and nested support flags)
- Verification evidence:
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression; D:/Compiler/anaconda/Scripts/activate; conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu -s applocation/NeuroLink/neuro_unit -d build/neurolink_unit` => PASS (`build/neurolink_unit/zephyr/zephyr.elf` linked)
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression; D:/Compiler/anaconda/Scripts/activate; conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu -s applocation/NeuroLink/neuro_unit/tests/app_command -d build/neurolink_unit_ut_app_command` => PASS (`build/neurolink_unit_ut_app_command/zephyr/zephyr.elf` linked)
- Open risks:
  - zenoh runtime override is currently memory-resident and reconnect-driven; persistent override storage across reboot is not landed yet in this slice
  - board-specific provider implementation still exists in-tree by planned two-stage migration strategy; port-layer generic-only cleanup (source removal) remains a follow-up slice
- Rollback notes:
  - rollback can restore old `feature_ops` schema and CMake compile definitions while keeping Kconfig symbols dormant, then remove shell override commands if needed
- Next action:
  - continue release-1.0.1 phase-2 cleanup by removing board-specific provider selection/implementation from active path and complete generic-only port layer convergence

#### EXEC-064 Release-1.0.1 Phase-2: Generic-Only Port Convergence

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/port/neuro_unit_port.h`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port.c`
  - `applocation/NeuroLink/neuro_unit/src/port/board_dnesp32s3b.c` (removed)
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/neuro_unit/Kconfig`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - converged Unit port layer to generic-only implementation by removing board-specific provider declaration, selection branch, and source file
  - simplified provider bootstrap so `neuro_unit_port_select_provider()` always returns `generic`
  - removed `CONFIG_NEURO_UNIT_PORT_FORCE_GENERIC` because provider forcing is no longer needed after generic-only convergence
  - updated runtime documentation to reflect generic-only port policy and integration rules
- UT added or updated:
  - no new source-level UT in this slice; behavior validated via build/link evidence
- Verification evidence:
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression; D:/Compiler/anaconda/Scripts/activate; conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu -s applocation/NeuroLink/neuro_unit -d build/neurolink_unit` => PASS (`build/neurolink_unit/zephyr/zephyr.elf` linked)
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression; D:/Compiler/anaconda/Scripts/activate; conda activate zephyr; west build -p always -b dnesp32s3b/esp32s3/procpu -s applocation/NeuroLink/neuro_unit/tests/app_command -d build/neurolink_unit_ut_app_command` => PASS (`build/neurolink_unit_ut_app_command/zephyr/zephyr.elf` linked)
- Open risks:
  - generic provider currently advertises no storage/network capability by design, so board-side operational flows depending on those ops are expected to return deterministic `NOT_SUPPORTED` until a replacement strategy is introduced
  - removal of board-specific provider narrows direct hardware adaptation surface; follow-up architecture work should define where board differentiation is injected while preserving generic-only policy
- Rollback notes:
  - rollback can restore `board_dnesp32s3b.c`, provider declaration/selection branch, and `CONFIG_NEURO_UNIT_PORT_FORCE_GENERIC` in one slice without touching runtime command ABI split work from `EXEC-063`
- Next action:
  - proceed to release-1.0.1 follow-up: finalize zenoh runtime override persistence across reboot and add targeted UT coverage for endpoint override priority (`runtime override > Kconfig default`)

#### EXEC-065 Release-1.0.1 Verification Closure Audit (UT/HW/Coverage)

- Status: blocked
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - completed a release-1.0.1 verification-closure audit for `EXEC-063` and `EXEC-064` to align ledger claims with currently reproducible evidence
  - verified UT runtime evidence is active for the qemu-based Linux path and can be tied to concrete summary/log artifacts rather than build-only assertions
  - initial audit observed coverage was still estimate-based at that point; quantified `tests/app_command` host-native coverage was subsequently captured in `EXEC-067`
  - verified historical hardware evidence contains both a fully passing window and earlier failure windows, so "all hardware items PASS" cannot be claimed yet for the latest `EXEC-063/064` baseline without a fresh full-matrix rerun
- UT added or updated:
  - no new source-level UT in this slice; audit-only ledger consolidation
- Verification evidence:
  - `applocation/NeuroLink/smoke-evidence/ut-runtime/20260413T171425Z/summary.txt`
    - `result=PASS`
    - `twister_native_sim_rc=0`
    - `qemu_build_rc=0`
    - `qemu_run_rc=124`
  - `applocation/NeuroLink/smoke-evidence/ut-runtime/20260413T171425Z/qemu_x86_64_run.log`
    - contains `TESTSUITE SUMMARY END`
    - contains `PROJECT EXECUTION SUCCESSFUL`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
    - `Current environment does not provide gcov/lcov runtime report for this UT target, so coverage below is a test-case to code-path estimation.`
  - `applocation/NeuroLink/docs/integration/HW_TEST_SESSION_2026-04-09.md`
    - contains historical passing closure window with `结果：全 PASS。`
    - also contains historical failure windows including `activate` failure and `no_reply` observations
- Open risks:
  - quantified coverage now exists for the `tests/app_command` target, but "UT complete coverage for entire project code" remains unproven because the captured scope is limited to the Unit source files included by that target
  - latest-baseline hardware full-matrix rerun is still missing, so "all hardware test items PASS" remains unproven for release-1.0.1 after `EXEC-063/064`
- Rollback notes:
  - documentation-only audit entry; rollback impact is limited to release traceability
- Next action:
  - execute and record a fresh hardware full matrix on the current `EXEC-063/064` baseline (`query device`, `lease acquire`, `prepare`, `verify`, `activate`, `query apps`, `rollback`, post-action `query device`), then update this audit entry to final closure

#### EXEC-066 Release-1.0.1 Quantified UT Coverage Workflow Scaffolding

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_coverage_linux.sh`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_coverage_from_windows.ps1`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - added a dedicated Linux coverage script for the `app_command` UT target that builds `native_sim` with `CONFIG_COVERAGE=y`, runs the host executable, captures lcov data, filters the report to `applocation/NeuroLink/neuro_unit/src/*`, and emits summary plus HTML artifacts
  - added a PowerShell wrapper that forwards the quantified coverage run into WSL so Windows-hosted workflows can trigger the Linux coverage path without retyping the translation logic
  - updated `TESTING.md` to document prerequisites, commands, generated artifacts, and the now-confirmed blocker for the current host (`gcc -m32` missing 32-bit libc development headers)
- UT added or updated:
  - no new source-level UT cases in this slice; test-infrastructure and evidence-generation workflow only
- Verification evidence:
  - `wsl -d Ubuntu bash -lc "cd /mnt/d/Software/project/zephyrproject && bash -n applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_coverage_linux.sh"` => PASS
  - `pwsh` parser validation of `run_ut_coverage_from_windows.ps1` => PASS
  - `wsl -d Ubuntu bash -lc "cd /mnt/d/Software/project/zephyrproject && west build -p always -b native_sim applocation/NeuroLink/neuro_unit/tests/app_command -d build/neurolink_unit_ut_native_sim_cov -- -DCONFIG_COVERAGE=y"` => reaches configure stage and coverage Kconfig enablement, then fails at compile with missing host header `bits/libc-header-start.h`
  - `build/neurolink_unit_ut_native_sim_cov/zephyr/.config` contains `CONFIG_COVERAGE=y` and `CONFIG_COVERAGE_NATIVE_GCOV=y`
- Open risks:
  - this slice only scaffolds the workflow; release evidence still depends on an actual captured coverage run being appended to the ledger
  - current quantified report scope is intentionally limited to `applocation/NeuroLink/neuro_unit/src/*`; it does not yet justify a claim of full-repository coverage
- Rollback notes:
  - rollback can remove the new coverage scripts and restore `TESTING.md` to estimate-only guidance without affecting runtime UT execution flow
- Next action:
  - execute the scaffolded host-native coverage run on `native_sim/native/64`, capture the generated artifact paths and metrics, and append them to the release ledger

#### EXEC-067 Release-1.0.1 Quantified UT Coverage Evidence Capture

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_coverage_linux.sh`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - switched quantified coverage execution from the blocked 32-bit `native_sim` path to the verified `native_sim/native/64` host path
  - executed the WSL-backed coverage workflow end-to-end and generated release-indexable coverage artifacts under `smoke-evidence/ut-coverage`
  - confirmed quantified coverage can now be stated for the `applocation/NeuroLink/neuro_unit/src/*` source-under-test scope while keeping `EXEC-065` blocked only on latest-baseline hardware full-matrix evidence
- UT added or updated:
  - no new source-level UT cases in this slice; evidence generation and quantified report capture only
- Verification evidence:
  - `(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression; D:/Compiler/anaconda/Scripts/activate; conda activate zephyr; Set-Location d:/Software/project/zephyrproject; $env:RUN_TIMEOUT_SEC='120'; pwsh applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_coverage_from_windows.ps1 -Distro Ubuntu` => PASS
  - `applocation/NeuroLink/smoke-evidence/ut-coverage/20260413T185058Z/summary.txt`
    - `result=PASS`
    - `build_rc=0`
    - `run_rc=0`
  - `applocation/NeuroLink/smoke-evidence/ut-coverage/20260413T185058Z/native_sim_run.log`
    - contains `TESTSUITE SUMMARY END`
    - contains `PROJECT EXECUTION SUCCESSFUL`
  - `applocation/NeuroLink/smoke-evidence/ut-coverage/20260413T185058Z/coverage_gcovr_summary.txt`
    - `lines: 65.2% (908 out of 1393)`
    - `functions: 85.0% (96 out of 113)`
    - `branches: 48.8% (558 out of 1143)`
  - `applocation/NeuroLink/smoke-evidence/ut-coverage/20260413T185058Z/coverage_html/index.html`
    - HTML coverage report generated successfully
- Open risks:
  - quantified coverage scope is limited to `applocation/NeuroLink/neuro_unit/src/*` included in the `tests/app_command` target; it is not evidence for full-repository coverage
  - release closure is still blocked on a fresh post-`EXEC-064` hardware full matrix with per-step PASS/FAIL evidence
- Rollback notes:
  - rollback can remove the host-native coverage execution route and keep previous estimate-only coverage guidance, without affecting UT source behavior
- Next action:
  - update `EXEC-065` final closure statement after a fresh hardware full matrix is executed and archived on the current release-1.0.1 baseline

#### EXEC-068 Release-1.0.1 Latest-Baseline Hardware Replay Blocker Confirmation

- Status: blocked
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/docs/integration/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - rebuilt, reflashed, and replayed the real-board validation entry sequence on `COM4` specifically against the current `EXEC-063/064` baseline
  - confirmed the post-flash board no longer reaches queryable ready state because the current generic-only provider does not expose storage/network preparation capability on `dnesp32s3b`
  - reproduced the blocker before the update matrix itself: post-flash `query device` and `query apps` both return `no_reply`, while serial logs remain at `network not ready yet`
  - verified shell-level preparation commands exist in help but are rejected at execution time with `command 'mount_storage' is not supported on this board` and `command 'network_connect' is not supported on this board`
- UT added or updated:
  - no source-level UT changes in this slice; on-device replay and blocker confirmation only
- Verification evidence:
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit -d build_neurolink_unit` => PASS
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m west build -d build_neurolink_unit -t neuro_unit_app_ext` => PASS
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m west flash -d build_neurolink_unit --esp-device COM4` => PASS
  - post-flash `query device` => FAIL (`status=no_reply`)
  - post-flash `query apps` => FAIL (`status=no_reply`)
  - serial monitor shows:
    - `unit port provider: generic`
    - `generic provider enabled for board: dnesp32s3b`
    - repeated `network not ready yet: state=ADAPTER_READY ifindex=1 iface_up=0 ipv4=no-ipv4`
    - `app mount_storage` => `command 'mount_storage' is not supported on this board`
    - `app network_connect cemetery goodluck1024` => `command 'network_connect' is not supported on this board`
  - implementation cross-check:
    - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic.c` configures `support.storage.* = false` and `support.network.* = false`
- Open risks:
  - release-1.0.1 latest baseline currently cannot satisfy hardware readiness prerequisites on the real board after generic-only convergence
  - full hardware matrix remains blocked until storage/network capability is reintroduced through an architecture-consistent mechanism
- Rollback notes:
  - documentation-only evidence slice; runtime rollback would require architectural choice, not ledger rollback alone
- Next action:
  - define and implement the generic-only compatible board capability injection path, then rerun the full hardware matrix and update `EXEC-065`

#### EXEC-069 Release-1.0.1 Generic Capability Injection and Hardware Matrix Closure

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic_dnesp32s3b.c`
  - `applocation/NeuroLink/neuro_unit/CMakeLists.txt`
  - `applocation/NeuroLink/docs/integration/HW_TEST_SESSION_2026-04-09.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - introduced a generic-provider capability injection hook (`neuro_unit_port_generic_board_caps_apply`) so the architecture remains generic-only while allowing board capability wiring
  - added `dnesp32s3b` injection implementation to restore storage/network ops (`mount_storage`, `network_connect`, `artifact_fetch`) and board storage paths (`/SD:/apps`, `/SD:/recovery.seed`)
  - rebuilt and reflashed latest baseline, then reran full real-board matrix to close the blocker captured by `EXEC-068`
- UT added or updated:
  - no new UT cases in this slice; focus was runtime capability restoration + on-device matrix replay
- Verification evidence:
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit -d build_neurolink_unit` => PASS
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m west build -d build_neurolink_unit -t neuro_unit_app_ext` => PASS
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m west flash -d build_neurolink_unit --esp-device COM4` => PASS
  - serial evidence includes:
    - `unit port provider: generic`
    - `board capability injection applied for dnesp32s3b`
    - `app mount_storage` => `storage mounted`
    - `app network_connect cemetery goodluck1024` => `network connect request sent`
  - full matrix replay on latest baseline:
    - `query device` => PASS (`status=ok`, `session_ready=true`, `network_state=NETWORK_READY`)
    - `lease-acquire(update/app/neuro_unit_app/activate)` => PASS (`lease-act-unit-101`)
    - `prepare(neuro_unit_app)` => PASS
    - `verify(neuro_unit_app)` => PASS
    - `activate(neuro_unit_app)` => PASS
    - `query apps` => PASS (`neuro_unit_app` running)
    - `lease-acquire(update/app/neuro_unit_app/rollback)` => PASS (`lease-rb-unit-101`)
    - `rollback(neuro_unit_app)` => PASS
    - post-rollback `query device` => PASS
- Open risks:
  - coverage remains scoped to `neuro_unit/src/*` exercised by `tests/app_command`; this slice does not change coverage scope boundaries
- Rollback notes:
  - if board capability injection introduces future regressions, rollback can disable `dnesp32s3b` injection implementation while retaining generic hook scaffolding for controlled re-enable
- Next action:
  - use `EXEC-069` evidence to update release closure gate (`EXEC-065`) from hardware-blocked to matrix-validated with explicit coverage-scope caveat

#### EXEC-070 Release-1.0.2 Remove HTTP App Download (Zenoh-Only)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Planning summary:
  - define release-1.0.2 transport simplification scope: remove HTTP artifact download support from Unit app-prepare path and board port capability wiring
  - keep Zenoh artifact transfer (`artifact_key` + chunked query/reply) as the only supported app download mechanism
  - deprecate and remove HTTP fallback surfaces in CLI and runtime request handling (`--url` compatibility path)
  - this slice is planning-only; no source implementation is performed in `EXEC-070`
- Verification target (for follow-up implementation slice):
  - `prepare --file` (Zenoh) remains PASS on real hardware
  - legacy HTTP `prepare --url` path is rejected with explicit unsupported/validation error
  - no HTTP socket download path remains reachable in production Unit runtime
- Open risks:
  - migration impact for any external tooling still invoking `prepare --url`
  - documentation and operator runbooks must be synchronized with Zenoh-only policy before release cut
- Rollback notes:
  - if Zenoh-only cutover exposes regressions, temporary rollback can re-enable HTTP compatibility behind an explicit feature gate for one release window
- Next action:
  - execute implementation slice for release-1.0.2: remove HTTP download code path and update CLI/runtime/docs/tests to Zenoh-only behavior

#### EXEC-071 Release-1.0.1 Completion Check and Build-Governance Hardening

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
  - `applocation/NeuroLink/docs/project/DIRECTORY_GOVERNANCE.md`
  - `applocation/NeuroLink/docs/project/CODE_STYLE_KERNEL_PLAN.md`
  - `applocation/NeuroLink/docs/README.md`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h`
  - `applocation/NeuroLink/scripts/build_neurolink.ps1`
  - `applocation/NeuroLink/scripts/verify_workspace_layout.ps1`
  - `applocation/NeuroLink/scripts/clean_generated_outputs.ps1`
  - `applocation/NeuroLink/CORE_DEMO.md`
  - `applocation/NeuroLink/DEMO_RUNBOOK.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - checked current release evidence and confirmed `release-1.0.1` completion baseline is available through existing UT runtime PASS artifacts, quantified UT coverage artifacts, and latest hardware replay closure entries
  - expanded `release-1.0.2` execution direction into an enforceable delivery baseline: Zenoh-only artifact prepare path, explicit rejection contract for legacy `--url`, and synchronized CLI/runtime/docs/tests cleanup
  - introduced canonical PowerShell build entrypoint (`build_neurolink.ps1`) that activates `conda zephyr` and rejects non-compliant output paths outside `build/<target>`
  - introduced workspace layout guard (`verify_workspace_layout.ps1`) and generated-output cleanup tool (`clean_generated_outputs.ps1`) to prevent and remediate root-level `build_*` / `twister-out*` drift
  - normalized top-level compatibility docs to pointer-only stubs and added a staged Linux-kernel-style convergence plan for future source normalization slices
  - added semantic comments on key runtime command structs to improve maintainability at API boundaries without behavior changes
- UT added or updated:
  - no new UT cases in this slice; this is governance/tooling/code-comment hardening
- Verification evidence:
  - governance now defines canonical build-script path and strict layout check commands under `DIRECTORY_GOVERNANCE.md`
  - build script enforces `build/<target>` path policy and runs in PowerShell + `conda activate zephyr`
  - layout-check script reports forbidden root generated directories and supports strict non-zero exit for release/CI gating
- Open risks:
  - existing historical ledger/evidence entries still include legacy `build_*` paths by design and should not be rewritten retroactively
  - Linux kernel style convergence is now staged and governed, but module-by-module normalization still requires dedicated follow-up implementation slices
- Rollback notes:
  - if script-based workflow causes temporary operator friction, fallback can keep script enforcement for CI/release while allowing temporary local manual commands that still honor `build/<target>`
- Next action:
  - execute `EXEC-070` implementation slice (remove HTTP prepare path) and open the first code-style normalization slice for `neuro_unit/include` + one runtime module under the new plan

#### EXEC-072 Release-1.0.2 Zenoh-Only Prepare Path Implementation (Phase 1)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py`
  - `applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py`
  - `applocation/NeuroLink/tests/test_core_cli.py`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic_dnesp32s3b.c`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_shell.c`
  - `applocation/NeuroLink/subprojects/unit_cli/docs/CORE_CLI_CONTRACT.md`
  - `applocation/NeuroLink/subprojects/unit_cli/docs/CORE_DEMO.md`
  - `applocation/NeuroLink/docs/integration/DEMO_RUNBOOK.md`
  - `.github/workflows/neurolink_unit_ut_linux.yml`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh`
  - `applocation/NeuroLink/CORE_DEMO.md` (removed)
  - `applocation/NeuroLink/DEMO_RUNBOOK.md` (removed)
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - removed CLI `--url` input path from both `prepare` and `deploy prepare`; `release_target` marker in CLI moved to `1.0.2`
  - changed Unit `handle_update_prepare` contract to Zenoh-only by requiring `artifact_key` and removing HTTP fallback execution branch
  - removed board HTTP download implementation and wiring from `dnesp32s3b` capability injection path; board now keeps storage mount + network connect but no HTTP artifact fetch hook
  - removed shell-level `artifact_fetch` command exposure to keep runtime command surface aligned with Zenoh-only release policy
  - updated canonical CLI/demo/runbook docs to remove HTTP fallback usage examples and document `--file`-only prepare policy
  - executed aggressive duplicate-doc cleanup by removing top-level compatibility copies (`CORE_DEMO.md`, `DEMO_RUNBOOK.md`) and keeping canonical docs only
  - hardened Linux UT workflow against build-output policy drift by forcing Twister output directory under `build/` and adding CI preflight guard that fails on root-level `build_*`/`twister-out*`
- UT added or updated:
  - updated parser UT in both canonical and compatibility test entrypoints from `--url` expectation to `--file` expectation
- Verification evidence:
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m unittest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` => PASS (`Ran 11 tests ... OK`)
  - `pwsh applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit` (PowerShell + `conda activate zephyr`) => PASS (`ninja: no work to do` after pristine build)
  - `pwsh applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ut -PristineAlways` (PowerShell + `conda activate zephyr`) => PASS (`zephyr.elf` linked)
  - source scan confirms canonical CLI no longer exposes `--url` and runbook/core demo no longer includes URL prepare examples
- Open risks:
  - `APP_RT_CMD_ARTIFACT_FETCH` enum/capability plumbing is still present in runtime command core for compatibility; current behavior is unsupported by config and no longer reachable from prepare or shell
  - historical/archive docs and historical ledger commands still contain old HTTP/build path text by design and are not rewritten retroactively
- Rollback notes:
  - rollback can restore CLI `--url` parser/options and Unit fallback branch in one slice, then re-enable board HTTP download/wiring if emergency compatibility is required
- Next action:
  - execute `EXEC-070` phase-2 cleanup: remove remaining artifact-fetch compatibility plumbing from runtime command ABI/tests if release owner confirms no downstream dependency, then run board full matrix with Zenoh-only prepare evidence capture

#### EXEC-073 Release-1.0.2 Runtime ABI Cleanup (Artifact-Fetch Removal)

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_cmd.h`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic.c`
  - `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic_dnesp32s3b.c`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/test_app_runtime_cmd_capability.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - removed `APP_RT_CMD_ARTIFACT_FETCH` from runtime command enum to align command ABI with Zenoh-only release policy
  - removed `support.network.artifact_fetch` and `network_ops.artifact_fetch` from runtime command config contract
  - removed artifact-fetch dispatcher branch from `app_runtime_cmd_exec`; runtime command plane now keeps `storage_mount/storage_unmount/network_connect` + lifecycle commands
  - removed residual artifact-fetch defaults and provider wiring in generic and `dnesp32s3b` capability injection paths
  - updated capability UT to stop asserting artifact-fetch behavior and keep only still-supported command-surface checks
- UT added or updated:
  - updated `test_app_runtime_cmd_capability.c` to remove artifact-fetch mock/hook assertions and unsupported-case checks for removed enum path
- Verification evidence:
  - source scan under `applocation/NeuroLink/neuro_unit/**` confirms no `APP_RT_CMD_ARTIFACT_FETCH` / `artifact_fetch` references remain in active code
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ut -Board qemu_x86_64 -BuildDir build/neurolink_unit_ut_qemu_x86_64_clean_20260414 -PristineAlways` (PowerShell + `conda activate zephyr`) => PASS (`zephyr.elf` linked)
  - `west build -d build/neurolink_unit_ut_qemu_x86_64_clean_20260414 -t run` => FAIL in Windows host env due missing `grep` in cmd pipeline for qemu image post-processing; not a compile regression from this slice
- Open risks:
  - qemu run target on current Windows host depends on `grep` in command pipeline; runtime execution evidence still requires either shell toolchain adjustment or Linux CI evidence path
  - historical progress entries retain generic `artifact_fetch` wording for past slices by design and are not rewritten retroactively
- Rollback notes:
  - rollback requires restoring enum value, config fields, dispatcher branch, provider wiring, and removed UT assertions in one consistent slice
- Next action:
  - execute board-side Zenoh-only full matrix evidence capture for release-1.0.2 and then start first Linux-kernel-style normalization implementation slice (`include/runtime` + one runtime source module)

#### EXEC-074 WSL UT Runtime Auto-Exit Fix and Policy Clarification

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/docs/project/DIRECTORY_GOVERNANCE.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - confirmed issue: UT run log reaches `PROJECT EXECUTION SUCCESSFUL` but qemu runtime could remain active and require manual interruption (`qemu_run_rc=130` observed in latest evidence before fix)
  - updated Linux UT runner to auto-detect PASS markers and proactively terminate qemu process, then normalize successful auto-stop path to `qemu_run_rc=0`
  - tightened result gate so PASS now requires both pass-pattern match and clean normalized run return code
  - clarified governance: Unit UT runtime evidence is Linux/WSL canonical; direct Windows-host `west build -t run` is non-canonical for release evidence
  - updated testing guide to document auto-exit behavior and expected signal-2 line during script-controlled qemu stop
- UT added or updated:
  - no new source UT cases; test-infra behavior fixed in `run_ut_linux.sh`
- Verification evidence:
  - `wsl -d Ubuntu bash -lc "cd /mnt/d/Software/project/zephyrproject && bash -n applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh"` => PASS
  - `wsl -d Ubuntu bash -lc "cd /mnt/d/Software/project/zephyrproject && RUN_TIMEOUT_SEC=240 bash applocation/NeuroLink/neuro_unit/tests/app_command/run_ut_linux.sh"` => PASS
  - latest runtime summary: `applocation/NeuroLink/smoke-evidence/ut-runtime/20260414T155125Z/summary.txt` shows `result=PASS` and `qemu_run_rc=0`
  - latest run log: `applocation/NeuroLink/smoke-evidence/ut-runtime/20260414T155125Z/qemu_x86_64_run.log` includes `PROJECT EXECUTION SUCCESSFUL` followed by script-driven qemu stop line and no manual Ctrl+C dependency
- Open risks:
  - qemu process stop currently uses `pkill -INT -f qemu-system-x86_64`, which assumes dedicated UT runtime host context; shared-host parallel qemu workloads should avoid concurrent execution
- Rollback notes:
  - rollback is limited to restoring previous run section in `run_ut_linux.sh`; no runtime firmware behavior changed
- Next action:
  - keep using `run_ut_from_windows.ps1 -> run_ut_linux.sh` as the only UT runtime evidence path and continue appending smoke-evidence summaries per execution slice

### 2026-04-15

#### EXEC-075 Documentation Convergence and CLI Skill Decoupling Cleanup

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/subprojects/unit_cli/README.md`
  - `applocation/NeuroLink/subprojects/unit_cli/skill/README.md`
  - `applocation/NeuroLink/core_cli.py` (removed)
  - `applocation/NeuroLink/tests/test_core_cli.py` (removed)
  - `applocation/NeuroLink/core_cli_skill/*` (removed)
  - `applocation/NeuroLink/core_demo.py` (removed)
  - `applocation/NeuroLink/docs/archive/*` (removed)
  - `applocation/NeuroLink/docs/integration/*` (removed)
  - `applocation/NeuroLink/docs/core_cli/*` (removed)
  - `applocation/NeuroLink/docs/neuro_unit/*` (removed)
  - `applocation/NeuroLink/docs/project/DIRECTORY_GOVERNANCE.md` (removed)
  - `applocation/NeuroLink/docs/project/CODE_STYLE_KERNEL_PLAN.md` (removed)
  - `applocation/NeuroLink/subprojects/unit_cli/docs/*` (removed)
  - top-level compatibility markdown wrappers (removed):
    - `applocation/NeuroLink/HLD.md`
    - `applocation/NeuroLink/AI_CORE_LLD.md`
    - `applocation/NeuroLink/UNIT_LLD.md`
    - `applocation/NeuroLink/LLD.md`
    - `applocation/NeuroLink/CORE_CLI_CONTRACT.md`
    - `applocation/NeuroLink/CORE_CLI_SKILLS_SCHEMA.md`
    - `applocation/NeuroLink/CORE_DEMO.md`
    - `applocation/NeuroLink/HW_TEST_SESSION_2026-04-09.md`
    - `applocation/NeuroLink/PHASE2_HANDOFF_2026-04-06.md`
    - `applocation/NeuroLink/AI_CORE_FRAMEWORK_DECISION_2026-04-07.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-UT-*`
  - `CORE-LLD-ARCH-*`
- Implementation summary:
  - applied a strict documentation keep policy so NeuroLink now retains only project progress ledger, project design docs, testing guide, and subproject README surfaces
  - removed all temporary/compatibility/core-demo documentation and wrappers that created duplicate ownership and cross-project coupling
  - removed legacy top-level `core_cli.py` and `core_cli_skill` compatibility path; `subprojects/unit_cli` is now the single CLI + skill subproject
  - removed all core demo artifacts and references from active project tree so no demo-only path remains in canonical execution surfaces
  - updated surviving README references to point at canonical testing and CLI skill entrypoints
- UT added or updated:
  - no source-level UT case changes in this slice; scope is project-structure/documentation convergence and decoupling cleanup
- Verification evidence:
  - file inventory scan now shows markdown set reduced to canonical retained set:
    - `applocation/NeuroLink/PROJECT_PROGRESS.md`
    - `applocation/NeuroLink/docs/project/HLD.md`
    - `applocation/NeuroLink/docs/project/AI_CORE_LLD.md`
    - `applocation/NeuroLink/docs/project/UNIT_LLD.md`
    - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
    - `applocation/NeuroLink/neuro_unit/README.md`
    - `applocation/NeuroLink/subprojects/unit_cli/README.md`
    - `applocation/NeuroLink/subprojects/unit_cli/skill/SKILL.md`
    - `applocation/NeuroLink/subprojects/unit_cli/skill/README.md`
  - reference scan confirms removed path patterns (`core_demo.py`, top-level `core_cli.py`, `core_cli_skill`, `docs/integration`, `docs/archive`, `subprojects/unit_cli/docs/*`) now only appear in historical ledger text
- Open risks:
  - historical entries in `PROJECT_PROGRESS.md` intentionally keep old file paths as immutable evidence and may reference removed compatibility paths
  - external personal scripts that still call deleted compatibility wrappers must migrate to canonical entrypoints under `subprojects/unit_cli`
- Rollback notes:
  - rollback can reintroduce removed compatibility wrappers and archive/integration docs from version control history without touching runtime firmware behavior
- Next action:
  - continue release-1.0.2 closure only on canonical paths (`subprojects/unit_cli` + `neuro_unit/tests/app_command/TESTING.md`) and reject any reintroduction of top-level compatibility wrappers

#### EXEC-076 Release-1.0.2 Closure Consolidation and Delivery Plan Expansion

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - consolidated release-1.0.2 closure by validating that Zenoh-only prepare policy is fully reflected on active code paths:
    - CLI prepare/deploy-prepare keep `--file` only
    - Unit prepare handler requires `artifact_key` and no HTTP fallback branch
    - runtime command ABI no longer contains `APP_RT_CMD_ARTIFACT_FETCH`
  - confirmed canonical project layout after compatibility-wrapper cleanup remains executable for active Unit and CLI development paths
  - treated `EXEC-070` planning objective as fulfilled by implementation/evidence chain `EXEC-072 + EXEC-073 + EXEC-076`
  - expanded post-closure plan to focus on release-1.0.3 hardening slices (style normalization + targeted selector/reconnect guard UT)
- UT added or updated:
  - no new source-level UT cases in this slice
  - local regression checks rerun for existing suites
- Verification evidence:
  - PowerShell + conda policy scan of active paths (`neuro_unit` + `subprojects/unit_cli`) finds no live `--url` / `APP_RT_CMD_ARTIFACT_FETCH` / `artifact_fetch` / `http(s)` implementation surface (historical ledger and smoke artifacts excluded by scope)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit -PristineAlways` => PASS (`ESP32-S3 image` generated)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ut -PristineAlways` => PASS (`build/neurolink_unit_ut_app_command/zephyr/zephyr.elf` linked)
  - `D:/Compiler/anaconda/envs/zephyr/python.exe -m unittest applocation/NeuroLink/subprojects/unit_cli/tests/test_core_cli.py` => PASS (`Ran 11 tests ... OK`)
- Open risks:
  - this closure slice provides code/build/test evidence on current workspace and host policy path; dedicated board replay for Zenoh-only prepare should continue to be captured in subsequent hardware execution slices when COM device session is scheduled
  - historical smoke/coverage artifacts still contain old symbol text by design and are not active-code regressions
- Rollback notes:
  - if emergency compatibility is needed, rollback path remains a coupled restore of CLI `--url` parser plus Unit prepare fallback branch and runtime ABI wiring in one slice
- Next action:
  - open release-1.0.3 kickoff slice with two priorities:
    - Linux-kernel-style normalization for `neuro_unit/include/runtime` and one selected runtime module
    - add focused UT for provider selector/transport guard branches where current confidence is still build/link dominant

#### EXEC-077 Release-1.0.2 Mandatory C-Style Enforcement and Key-Comment Normalization

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/.clang-format`
  - `applocation/NeuroLink/scripts/format_neurolink_c_style.ps1`
  - `applocation/NeuroLink/scripts/build_neurolink.ps1`
  - `applocation/NeuroLink/neuro_unit/src/neuro_state_registry.c`
  - `applocation/NeuroLink/neuro_unit/include/*` (formatted)
  - `applocation/NeuroLink/neuro_unit/src/*` (formatted)
  - `applocation/NeuroLink/neuro_unit/tests/app_command/src/*` (formatted)
  - `applocation/NeuroLink/neuro_unit/README.md`
  - `applocation/NeuroLink/neuro_unit/tests/app_command/TESTING.md`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - introduced a repository-local C formatting baseline in `neuro_unit/.clang-format` with Linux-kernel-like constraints (`tab=8`, Linux brace style, 80-column limit)
  - added a dedicated style tool `format_neurolink_c_style.ps1` supporting both `-CheckOnly` and `-Fix` execution paths over all active Unit C/H scopes
  - integrated mandatory style gate into canonical build entry `build_neurolink.ps1` (`CheckCStyle=true` by default), making style compliance a pre-build requirement
  - performed full normalization for active Unit C/H files (include/src/tests) so current baseline starts from a clean style state
  - added key maintainability comments in `neuro_state_registry.c` around snapshot version monotonicity and lock-protected read coherence
  - updated README and testing guide so future contributors must run/check style under PowerShell + conda policy before accepting build/test evidence
- UT added or updated:
  - no new source-level UT cases in this slice
  - UT target build path now includes mandatory style-gate precheck via canonical build script
- Verification evidence:
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -CheckOnly` => initially failed with 46 files
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -Fix` => formatted 46 files
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -CheckOnly` => PASS (`c-style check passed (46 files)`)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ut` => PASS (style check + UT target `zephyr.elf` link success)
- Open risks:
  - `clang-format` Linux preset is unavailable in current toolchain, so this slice uses LLVM base plus explicit Linux-kernel-like rules; behavior should be revalidated if toolchain version changes
  - style normalization was applied project-locally for active Unit scope; external modules outside NeuroLink Unit remain governed by their own standards
- Rollback notes:
  - rollback can disable style gate by setting `CheckCStyle=false` default in `build_neurolink.ps1` and removing the new formatter script/config while keeping functional runtime code unchanged
- Next action:
  - keep style gate mandatory for all future Unit slices and add CI-level style-check step reusing `format_neurolink_c_style.ps1 -CheckOnly`

#### EXEC-078 Release-1.0.2 CI Style Gate Integration and Core Comment Hardening

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `.github/workflows/neurolink_unit_ut_linux.yml`
  - `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_cmd.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-ARCH-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - extended the existing Linux UT workflow with a dedicated `c-style-check` job so active NeuroLink Unit C/H changes are rejected in CI before UT execution when style drifts from the enforced baseline
  - wired the UT Linux job to depend on the new style gate, keeping one consistent path from local build script enforcement to CI enforcement
  - added focused maintainability comments to `app_runtime_cmd.c` around default config semantics, partial-config default filling, defensive fallback, and deterministic capability-gated dispatch contract
  - added focused maintainability comments to `neuro_unit.c` around auxiliary zenoh session usage and synchronous artifact materialization in the prepare path, documenting why nested artifact transfer must not reuse the control-plane session
- UT added or updated:
  - no new source-level UT cases in this slice
  - existing UT build path now inherits both local and CI style-gate enforcement
- Verification evidence:
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -CheckOnly` => initially failed on `neuro_unit.c` and `app_runtime_cmd.c` after comment insertion, confirming gate behavior
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -Fix` => normalized the touched files back to compliant format
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -CheckOnly` => PASS (`c-style check passed (46 files)`)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ut` => PASS (`build/neurolink_unit_ut_app_command/zephyr/zephyr.elf` linked)
- Open risks:
  - CI style gate currently lives inside the existing Linux UT workflow; if a future standalone style workflow is preferred for faster feedback, split-out can be done later without changing rule semantics
  - comment hardening in this slice focused on two highest-value runtime files; other complex runtime modules may still benefit from similarly selective comment additions in future maintenance slices
- Rollback notes:
  - rollback can remove the `c-style-check` CI job and the new comments without changing runtime behavior, while local build-script style gate remains independently reversible from `EXEC-077`
- Next action:
  - continue selective key-comment hardening on remaining high-complexity modules only where lifecycle or concurrency reasoning is otherwise non-obvious

#### EXEC-079 Release-1.0.2 Update/Recovery/LLEXT Comment Hardening Continuation

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_update_manager.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_recovery_seed_store.c`
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit_app_llext.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-SM-*`
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - extended selective key-comment coverage into the update manager state machine, documenting prepare admission semantics, two-stage rollback intent (`ROLLBACK_PENDING -> ROLLING_BACK`), and conservative reboot reconciliation policy
  - extended selective key-comment coverage into recovery-seed persistence, documenting fixed-layout v1 on-storage entries, versioned decode intent, `.tmp` recovery semantics, snapshot merge/split responsibilities, and tmp-write + sync + rename save policy
  - added concise contract comments to the sample LLEXT app so the exported command name, manifest role, fixed JSON callback behavior, and ABI symbol-export block are explicit for future maintainers and test authors
  - preserved the rule from earlier slices: comments remain selective and only explain non-obvious lifecycle/persistence/ABI behavior
- UT added or updated:
  - no new source-level UT cases in this slice
  - existing style/build gates were rerun against the updated files
- Verification evidence:
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -CheckOnly` => initially failed on the three touched files, confirming mandatory style gate enforcement
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -Fix` => normalized the touched files back to compliant format
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -CheckOnly` => PASS (`c-style check passed (46 files)`)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit` => PASS (`build/neurolink_unit/zephyr/zephyr.elf` linked)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ext` => PASS (`build/neurolink_unit/llext/neuro_unit_app.llext` generated)
- Open risks:
  - current `neuro_unit.c` still emits existing `snprintk` truncation warnings on prepare-path telemetry/JSON assembly; this slice did not change that behavior and the warning remains a follow-up cleanup item
  - comment hardening still intentionally avoids broad comment expansion across trivial code paths, so future slices should continue using a selective standard instead of blanket commenting
- Rollback notes:
  - rollback can remove the new explanatory comments without changing runtime or LLEXT behavior; style gate baseline remains governed by `EXEC-077` and CI gate by `EXEC-078`
- Next action:
  - close the remaining `snprintk` truncation warnings in `neuro_unit.c` with bounded formatting helpers so release builds stay warning-clean on the hot update path

#### EXEC-080 Release-1.0.2 Prepare-Path Warning Cleanup

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-DATA-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - removed the remaining prepare-path `snprintk` truncation warnings by resizing the two local buffers that were carrying variable-width content:
    - stage telemetry label buffer increased from `48` to `64`
    - prepare success reply buffer switched from fixed `256` to `NEURO_MAX_JSON_LEN`
  - kept protocol behavior unchanged while aligning buffer sizing with the already-defined project JSON size ceiling
- UT added or updated:
  - no new source-level UT cases in this slice
- Verification evidence:
  - `pwsh -File applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -CheckOnly` => PASS (`c-style check passed (46 files)`)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit` => PASS; previous prepare-path `-Wformat-truncation` warnings no longer appear
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ext` => PASS (`ninja: no work to do`)
- Open risks:
  - build output still contains pre-existing `zenoh-pico` macro redefinition warnings (`Z_FEATURE_SUBSCRIPTION`, `Z_FEATURE_LINK_UDP_MULTICAST`); these are external/module-integration warnings, not caused by the prepare-path code
- Rollback notes:
  - rollback is one-slice reversible by restoring the former buffer sizes, though doing so would reintroduce the same compiler diagnostics
- Next action:
  - decide whether to open a dedicated warning-cleanup slice for the remaining `zenoh-pico` integration warnings or keep them as accepted third-party noise with explicit documentation

#### EXEC-081 Release-1.0.2 Zenoh-Pico Zephyr Integration Warning Cleanup

- Status: completed
- Owner: GitHub Copilot with user direction
- Touched files:
  - `modules/lib/zenoh-pico/zephyr/CMakeLists.txt`
  - `modules/lib/zenoh-pico/zephyr/zenoh_generic_config.h.in`
  - `applocation/NeuroLink/PROJECT_PROGRESS.md`
- Linked LLD sections:
  - `UNIT-LLD-CODE-*`
  - `UNIT-LLD-UT-*`
- Implementation summary:
  - traced the remaining build warnings to the Zephyr-side zenoh-pico integration, where `CONFIG_ZENOH_PICO_*` values were being exported as `-D Z_FEATURE_*` compiler definitions while `include/zenoh-pico/config.h` also carried a second CMake-generated feature set
  - replaced that dual-source configuration path with a single generated Zephyr-side header: `zenoh_generic_config.h`
  - kept `ZENOH_ZEPHYR` for platform selection, added `ZENOH_GENERIC` only for config selection, and generated the feature/value header from Zephyr/Kconfig inputs so the library now consumes one authoritative feature map during Zephyr builds
  - fixed the first-pass template mistake by switching from `config.h.in` to a dedicated guard-free `zenoh_generic_config.h.in`, avoiding include-guard short-circuiting when `config.h` includes the generated Zephyr config
- UT added or updated:
  - no new source-level UT cases in this slice
  - build verification was rerun on both main Unit and LLEXT paths because the change sits in shared module integration
- Verification evidence:
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit -PristineAlways` => PASS (`build/neurolink_unit/zephyr/zephyr.elf` linked)
  - `pwsh -File applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ext` => PASS (`build/neurolink_unit/llext/neuro_unit_app.llext` generated)
  - the previous `zenoh-pico` macro redefinition warnings for `Z_FEATURE_SUBSCRIPTION` and `Z_FEATURE_LINK_UDP_MULTICAST` no longer appear in the Unit build log
- Open risks:
  - this slice intentionally fixes the Zephyr integration inside the vendored/module tree, so future upstream `zenoh-pico` updates may need the same integration strategy re-applied if the module is refreshed wholesale
- Rollback notes:
  - rollback can restore the former Zephyr compile-definition path, but doing so would reintroduce duplicate feature-definition warnings and reopen the risk of Kconfig values diverging from the header-visible feature map
- Next action:
  - if desired, run the Linux/WSL canonical UT evidence path once more to produce a fresh post-cleanup runtime evidence set on top of the now warning-clean build baseline
