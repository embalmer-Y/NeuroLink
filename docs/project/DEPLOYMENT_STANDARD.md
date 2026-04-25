# NeuroLink Host Deployment Standard

## 1. Objective

This document defines the enterprise-style host deployment standard for NeuroLink.
It separates Linux canonical execution from Windows compatibility execution so scripts,
dependencies, evidence, and troubleshooting are auditable and repeatable.

## 2. Host Roles

### 2.1 Linux Canonical Host

1. Linux is the canonical host for Release 1.1.0 build, style gate, UT runtime, coverage, and CI.
2. Linux-native entrypoints must exist for every release-critical workflow.
3. Linux evidence is the release signoff baseline unless a slice explicitly documents an exception.

### 2.2 Windows Compatibility Host

1. Windows remains supported for developer entry, board flashing, and WSL bridge workflows.
2. PowerShell scripts are compatibility wrappers unless they are explicitly documented as canonical.
3. Windows-only assumptions must not be introduced into canonical Linux workflows.

### 2.3 WSL Ubuntu Router Host

1. WSL Ubuntu may host `zenohd` for release-1.1.0 board-smoke migration work when the lab machine still depends on a Windows workstation.
2. WSL is not the canonical board build or serial host; it is a router-host compatibility layer unless a slice explicitly documents otherwise.
3. If Linux runs inside WSL, USB device passthrough must be established before any flash or serial evidence is treated as valid.

## 3. Script Standard

### 3.1 Environment Bootstrap

1. Linux bootstrap: `applocation/NeuroLink/scripts/setup_neurolink_env.sh`; this is the canonical entrypoint for repository-local `.venv` activation on Linux.
2. Windows bootstrap: `applocation/NeuroLink/scripts/setup_neurolink_env.ps1`
3. Bootstrap scripts must validate required tools, set repository-scoped environment variables, and report missing optional tools separately.
4. Linux `--strict` mode validates the required build contract; optional validation capabilities remain non-blocking until a runtime script explicitly requires them.
5. Linux bootstrap may also install the tracked Neuro CLI Python dependency set with `--install-unit-cli-deps` when the active `.venv` is missing host-side smoke/control packages.

### 3.2 Build and Style Entry Points

1. Linux build wrapper: `applocation/NeuroLink/scripts/build_neurolink.sh`
2. Windows build wrapper: `applocation/NeuroLink/scripts/build_neurolink.ps1`
3. Linux style gate: `applocation/NeuroLink/scripts/format_neurolink_c_style.sh`, `applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
4. Windows style gate: `applocation/NeuroLink/scripts/format_neurolink_c_style.ps1`, `applocation/NeuroLink/scripts/check_neurolink_linux_c_style.ps1`

### 3.3 Cleanup and Hygiene

1. Linux Zone.Identifier cleanup: `applocation/NeuroLink/scripts/clean_zone_identifier.sh`
2. Windows Zone.Identifier cleanup: `applocation/NeuroLink/scripts/clean_zone_identifier.ps1`
3. Generated-output cleanup remains in `applocation/NeuroLink/scripts/clean_generated_outputs.ps1` until a Linux pair is required.

### 3.4 Board Smoke and Router Entry Points

1. Linux board smoke helper: `applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`
2. Linux board/router preflight helper: `applocation/NeuroLink/scripts/preflight_neurolink_linux.sh`
3. Linux UART monitor helper: `applocation/NeuroLink/scripts/monitor_neurolink_uart.sh`
4. Board-bound WSL recovery helper for the validated lab board: `applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh`
5. WSL zenoh router installer: `applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh`
6. WSL zenoh router runner: `applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh`
7. Runbook for Linux board attach plus WSL router: `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md`
8. The WSL router installer may use either the official Debian repository (`apt`) or a user-local standalone package fallback when `sudo` is unavailable.
9. `smoke_neurolink_linux.sh` must run `preflight_neurolink_linux.sh` by default and must fail when reply payloads report protocol-level `status=error`, even if `neuro_cli.py` exits successfully.

## 4. Dependency Contract

### 4.1 Linux Required Tools

1. `python3`
2. `west`
3. `cmake`
4. `ninja`
5. `clang-format`
6. `perl`

Optional but expected for full validation:

1. `gcovr`
2. `qemu-system-x86_64`
3. `ZEPHYR_SDK_INSTALL_DIR` or a discoverable Zephyr SDK install

Notes:

1. Missing optional tools must be reported clearly, but they must not block the canonical `unit-ut` build bootstrap.
2. Runtime scripts that actually execute QEMU or coverage collection remain responsible for enforcing those tools when that path is selected.
3. Linux Python dependencies are expected in the repository-local `.venv`; Linux canonical flows do not rely on conda.
4. Board-oriented NeuroLink builds require the `zenoh-pico` Zephyr module to be materialized from `zephyr/submanifests/zenoh-pico.yaml` into `modules/lib/zenoh-pico` via `west update`.
5. Neuro CLI host-side Python dependencies are sourced from `applocation/NeuroLink/neuro_cli/requirements.txt`; bootstrap and smoke helpers must point to that file rather than a hard-coded one-off package command.

### 4.2 Windows Required Tools

1. PowerShell
2. `conda` environment `zephyr` or an equivalent validated environment
3. `west`
4. `cmake`
5. `ninja`
6. `clang-format`
7. `perl` or WSL for `checkpatch.pl`

## 5. Canonical Commands

### 5.1 Linux

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ut --pristine-always
bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh
bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_linux.sh
```

Board/runtime Linux presets that link against `zenoh-pico` require `west update zenoh-pico` or `west update` before the first build.

### 5.2 Windows

```powershell
. applocation/NeuroLink/scripts/setup_neurolink_env.ps1 -Activate -Strict
pwsh applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ut -PristineAlways
pwsh applocation/NeuroLink/neuro_unit/tests/unit/run_ut_from_windows.ps1
pwsh applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_from_windows.ps1
```

### 5.3 Linux Board Smoke with WSL Router

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --pristine-always
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ext
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset flash-unit --esp-device /dev/ttyUSB0
bash applocation/NeuroLink/scripts/monitor_neurolink_uart.sh --device /dev/ttyACM0
bash applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh
bash applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh --listen tcp/0.0.0.0:7447
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --wifi-ssid <ssid> --wifi-credential <credential>
bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh
```

If Linux is running inside WSL, the USB device must be attached into WSL before the flash command can succeed.

## 6. Copy and Migration Hygiene

1. If the repository is copied from Windows to Linux, run the Zone.Identifier cleanup script before build or test execution.
2. Preview first, then execute deletion explicitly.
3. Keep the cleanup result out of release ambiguity by recording it in the progress ledger when it affects active work.

## 7. Governance Rules

1. Every new release-critical Linux script must have either a Windows compatibility pair or an explicit justification for Linux-only scope.
2. Every new Windows compatibility wrapper must point to a canonical Linux path when one exists.
3. Documentation must state whether a script is canonical, compatibility-only, or transitional.
4. Release evidence must identify host platform, entrypoint script, and dependency context.
