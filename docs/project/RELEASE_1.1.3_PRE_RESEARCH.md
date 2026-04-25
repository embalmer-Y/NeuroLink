# NeuroLink Release 1.1.3 Pre-Research Baseline

## 1. Scope

Release 1.1.3 focuses on architecture and quality optimization after release-1.1.2 closure.

Primary goals:

1. Improve extensibility and reuse by clarifying code-layer responsibilities.
2. Expand port abstractions for filesystem and network capabilities.
3. Split UART shell from runtime implementation.
4. Extract zenoh transport/session logic from `neuro_unit.c` into dedicated modules with helper headers.

Out of scope for kickoff slice:

1. Protocol key/path changes.
2. JSON reply-shape changes.
3. CLI behavior changes.
4. Large runtime behavioral redesign.

## 2. Current Baseline

Release-1.1.2 closure is already recorded and validated in:

1. `applocation/NeuroLink/PROJECT_PROGRESS.md`
2. `applocation/NeuroLink/docs/project/RELEASE_1.1.2_QUALITY_BASELINE.md`
3. `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260423-185830.ndjson`

Current coupling hotspots:

1. `applocation/NeuroLink/neuro_unit/src/neuro_unit.c`
   - now mostly orchestration/business dispatch glue after `EXEC-109`; remaining coupling is around business handlers and shared service ownership.
2. `applocation/NeuroLink/neuro_unit/src/zenoh/neuro_unit_zenoh.c`
   - owns zenoh transport/session lifecycle, endpoint override, queryable declaration, reply/publish helpers, TCP probe, connect monitoring, and artifact download using port filesystem ops.
3. `applocation/NeuroLink/neuro_unit/src/shell/`
   - shell command surface is now separated from runtime and split by command responsibility: registration/shared helpers, lifecycle/status, storage, network, and zenoh connect override handling.
   - `include/shell/neuro_unit_shell.h` exposes the section-backed `app` command extension surface so future board/provider commands can attach without editing the core shell registration file.
4. `applocation/NeuroLink/neuro_unit/src/port/neuro_unit_port_generic_dnesp32s3b.c`
   - board-specific SD/Wi-Fi logic now publishes port filesystem/network ops; follow-on work can fill status/probe hooks and migrate more filesystem callsites.

## 3. Workstreams

### WS-1 Port Layer Contract Expansion

1. Add explicit port filesystem operations contract:
   - mount/unmount/stat/mkdir/remove/rename
   - open/read/write/close
   - opendir/readdir/closedir
   - caller migration now covers runtime artifact loading, zenoh artifact download, and update artifact availability checks.
2. Add explicit port network operations contract:
   - connect/disconnect
   - status collection through `get_status`; endpoint probe ownership through `probe_endpoint` when a provider supplies one.
3. Keep current board behavior unchanged in first slices.

### WS-2 Shell/Runtime Decoupling

1. Move UART shell registration and handlers into a dedicated shell module.
2. Keep runtime focused on LLEXT lifecycle operations.
3. Preserve existing command names and user-visible behavior during migration.
4. Provide a shell extension surface for board/provider commands while preserving the current `app` root command and existing subcommand behavior.

### WS-3 Zenoh Transport Extraction

1. Extract connect/session/queryable/reply/publish/fetch/probe logic from `neuro_unit.c`.
2. Introduce helper headers and module boundaries for transport ownership.
3. Keep follow-on migration focused on handler-level boundaries and real download callsites once prepare/download wiring resumes.

## 4. Acceptance Criteria

1. `neuro_unit.c` is reduced to composition and orchestration glue, not transport implementation.
2. Port API can host board-specific filesystem/network specializations without changing upper-layer callsites.
3. Shell module no longer lives inside runtime implementation.
4. Unit tests/build/smoke gates remain green with no behavior regression.

## 5. Verification Gates

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`
2. `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
3. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check`
4. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check`
5. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
6. when lab is available, rerun Linux preflight/smoke for real-device evidence.

## 6. Initial Execution Slices

1. `EXEC-107`: release-1.1.3 kickoff + port fs/network contract scaffolding.
2. `EXEC-108`: shell-module extraction baseline.
3. `EXEC-109`: zenoh transport helper/module extraction baseline.
4. `EXEC-112`: port filesystem contract unit coverage and runtime storage dispatch proof.
5. `EXEC-113`: removed legacy `storage_ops`/`network_ops` fields from `app_runtime_cmd_config` after port dispatch coverage landed.
6. `EXEC-114`: routed network manager status collection through port network `get_status` and added DNESP32S3B/native_sim coverage.
7. `EXEC-115`: routed zenoh endpoint probe entry through port network `probe_endpoint` while preserving socket fallback behavior.
8. `EXEC-116`: split shell command handlers by responsibility while preserving command names, help strings, arity, and user-visible behavior boundaries.
9. `EXEC-117`: added the public shell extension surface for the existing `app` command root using wrappers around Zephyr section-backed subcommand registration.
10. `EXEC-118`: recorded closure-tail decisions and attempted hardware/router preflight; router was listening, but serial hardware was not visible so smoke remained blocked.
11. `EXEC-119`: attached the CH343 board serial device into WSL, added `prepare_dnesp32s3b_wsl.sh --attach-only`, and narrowed the remaining preflight failure to board network/queryability rather than serial visibility.
12. `EXEC-120`: added lab Wi-Fi fallback defaults to `prepare_dnesp32s3b_wsl.sh`, restored board network readiness, and captured passing real-device preflight/smoke evidence.

## 7. Risks

1. Transport/session lifetime regressions during zenoh extraction if closure ownership changes too quickly.
2. Accidental protocol response drift if helper migration mixes behavior and structure changes in one slice.
3. Board-specific assumptions hidden in current shell/runtime flow may surface during decoupling.
4. Hardware/router preflight and smoke replay remain pending after the latest closure-tail slice; do not claim full release closure until that evidence is available or explicitly scoped out.

## 8. Rollback Strategy

1. Keep each slice behavior-preserving and independently reversible.
2. If regressions appear, rollback the current slice only; avoid cross-slice partial reverts.
3. Preserve tests and evidence updates even when behavior rollback is needed, so regression signatures remain captured.

## 9. Closure Tail Decisions (2026-04-25)

1. Opaque Unit query/reply context is deferred to a follow-up slice. Release-1.1.3 already wraps zenoh-pico helpers without changing behavior, and hiding `z_loaned_query_t` should wait for broader transport wrapper tests.
2. Deeper `app_runtime_cmd` rename or extraction is deferred. After legacy storage/network hook removal, the remaining module is an acceptable thin command facade unless a concrete ownership bug appears.
3. DNESP32S3B provider-specific endpoint probing is deferred until hardware replay is available. The current port hook path preserves provider extensibility while the zenoh socket fallback remains the validated behavior.
4. Hardware/router gate is not closed in this session. Preflight reached a listening router but failed with `status=serial_device_missing`, `serial_present=0`, and no visible `/dev/ttyACM*` or `/dev/ttyUSB*` device; real-device smoke was not run.
5. Release-1.1.3 should not be marked fully closed until the DNESP32S3B serial device is visible and both canonical Linux preflight and smoke pass, or until release ownership explicitly scopes out real-device evidence with this risk accepted.

## 10. Hardware Gate Recovery Note (2026-04-25)

1. The attached board was visible to Windows usbipd as CH343 BUSID `7-4` in `Shared` state but was not initially attached into WSL, explaining the earlier `serial_device_missing` classification.
2. After `usbipd.exe attach --wsl --busid 7-4`, Linux exposed `/dev/ttyACM0` and `prepare_dnesp32s3b_wsl.sh --attach-only --busid 7-4` passed.
3. Canonical preflight now reaches `status=no_reply_board_unreachable` with serial present, so the remaining blocker is board network/queryability, not host serial visibility.
4. UART diagnostics showed the shell and `app` command surface are present, while network readiness still reported `ADAPTER_READY`, `iface_up=0`, and `ipv4=no-ipv4`.
5. Follow-up `EXEC-120` added lab Wi-Fi fallback defaults and restored the real-device gate: board preparation with defaults reached `NETWORK_READY`, canonical preflight returned `ready=1`, and real-device smoke passed with evidence `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-043004.ndjson`.

## 11. Real-Device Recovery Evidence (2026-04-25)

1. `prepare_dnesp32s3b_wsl.sh` now defaults to the validated lab Wi-Fi values when no command-line or environment override is provided.
2. Board preparation with defaults passed on BUSID `7-4`, exposing `/dev/ttyACM0`, reaching `NETWORK_READY`, and returning `query_status=ok`.
3. Canonical preflight passed with `ready=1`, `query_status=ok`, and `serial_devices=/dev/ttyACM0`.
4. Canonical real-device smoke passed with `result=PASS` and evidence `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-043004.ndjson`.

## 12. Closure Review (2026-04-25)

Release-1.1.3 is closed against the current workspace state as a structure-and-quality release.

Development status: completed.

Acceptance criteria review:

1. `neuro_unit.c` is reduced to orchestration glue: satisfied.
   - zenoh session/queryable/reply/publish/fetch/probe ownership lives in `src/zenoh/neuro_unit_zenoh.c`
   - filesystem artifact paths and network status/probe hooks route through port contracts where release-1.1.3 scoped them
2. Port API can host board-specific filesystem/network specializations: satisfied.
   - port filesystem and network operation tables are present and covered by native_sim tests
   - DNESP32S3B publishes storage and Wi-Fi operations through the port layer
3. Shell module no longer lives inside runtime implementation: satisfied.
   - shell registration and handlers are split under `src/shell/`
   - `include/shell/neuro_unit_shell.h` provides an extension surface for future board/provider commands
4. Unit/build/script/real-device gates remain green: satisfied.
   - native_sim Unit regression, Linux Unit wrapper, unit-app/unit-edk builds, C style gate, and Linux script regression suite all passed during the closure tail
   - canonical real-device preflight and smoke passed after DNESP32S3B WSL attach and lab Wi-Fi default recovery
5. Release identity matches delivered state: satisfied.
   - `applocation/NeuroLink/subprojects/unit_cli/src/core_cli.py` now advertises `RELEASE_TARGET = "1.1.3"`

Closure evidence:

1. C style gate: `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh` => PASS (`0` errors; existing warnings remain non-blocking)
2. native_sim Unit regression: `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run` => PASS
3. Linux Unit wrapper: `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh` => PASS
4. unit-app build: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check` => PASS
5. unit-edk build: `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check` => PASS
6. script regression suite: `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh` => PASS (`7/7`)
7. real-device smoke: `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5` => PASS, evidence `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260425-043004.ndjson`

Residual notes:

1. The lab Wi-Fi default in `prepare_dnesp32s3b_wsl.sh` is intentionally scoped to local test convenience; non-lab deployments should pass explicit credentials or environment overrides.
2. Opaque Unit query/reply context, deeper `app_runtime_cmd` rename/extraction, and DNESP32S3B provider-specific endpoint probe remain follow-up candidates rather than release-1.1.3 closure blockers.
3. Follow-on work should open a new release or maintenance slice rather than extend release-1.1.3.
