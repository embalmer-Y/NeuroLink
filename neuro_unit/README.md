# NeuroLink Unit Runtime

该工程是 NeuroLink 的独立 Unit 项目，不再依赖 `app_runtime_llext` 目录源码。运行时、命令层、异常层与板级 port 已内置到当前工程，并在此基础上提供基于 `zenoh-pico` 的四平面最小闭环。phase2 起，Update Plane 默认支持通过 Zenoh 分块拉取 `.llext`。

- `Command Plane`
  - `neuro/unit-01/cmd/lease/acquire`
  - `neuro/unit-01/cmd/lease/release`
  - `neuro/unit-01/cmd/app/<app-id>/<command-name>`
  - `neuro/unit-01/cmd/app/<app-id>/start`
  - `neuro/unit-01/cmd/app/<app-id>/stop`
- `Query Plane`
  - `neuro/unit-01/query/device`
  - `neuro/unit-01/query/apps`
  - `neuro/unit-01/query/leases`
- `Event Plane`
  - `neuro/unit-01/event/state`
  - `neuro/unit-01/event/update`
  - `neuro/unit-01/event/lease/<lease-id>`
- `Update Plane`
  - `neuro/unit-01/update/app/<app-id>/prepare`
  - `neuro/unit-01/update/app/<app-id>/verify`
  - `neuro/unit-01/update/app/<app-id>/activate`

## Dependencies

- The NeuroLink Unit project depends on `zenoh-pico` for Command/Query/Event/Update plane communication.
- Linux host-side control/smoke tooling also depends on the Python package set in `applocation/NeuroLink/subprojects/unit_cli/requirements.txt` because `core_cli.py` imports `zenoh` from `eclipse-zenoh`.
- Keep `zephyr/submanifests/zenoh-pico.yaml` in the repository. This submanifest is the source of truth for materializing `modules/lib/zenoh-pico` through west's Zephyr module flow.
- Linux hosts use the repository-local `.venv` through `setup_neurolink_env.sh`; Linux canonical workflows do not use conda.
- If module sources are missing locally, run `west update zenoh-pico` or `west update` from the workspace root before building. Board/runtime builds now fail early until `modules/lib/zenoh-pico` is present.
- Cross-platform host deployment rules, script ownership, and dependency policy are defined in `applocation/NeuroLink/docs/project/DEPLOYMENT_STANDARD.md`.

Control-plane / smoke host dependency install:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict
python3 -m pip install -r applocation/NeuroLink/subprojects/unit_cli/requirements.txt
```

Equivalent bootstrap-assisted install:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps
```

## Build

### Linux canonical path

Linux canonical execution uses the repository-local `.venv` activated by `setup_neurolink_env.sh`, not a conda environment.

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --pristine-always
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ext
```

### Windows compatibility path

```powershell
. applocation/NeuroLink/scripts/setup_neurolink_env.ps1 -Activate -Strict
pwsh applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit -PristineAlways
pwsh applocation/NeuroLink/scripts/build_neurolink.ps1 -Preset unit-ext
```

Build gate note:

- `build_neurolink.ps1` now runs a mandatory Linux-style C check before build by default.
- `build_neurolink.sh` is the Linux-native peer for the same preset model and should be treated as the canonical local build entrypoint for release-1.1.0 work.
- The check target is `neuro_unit/include`, `neuro_unit/src`, and `tests/unit/src`.
- The gate now has two layers:
  - `format_neurolink_c_style.ps1` keeps formatter-controlled layout aligned to the local Linux-kernel-like `.clang-format` baseline.
  - `check_neurolink_linux_c_style.ps1` runs `zephyr/scripts/checkpatch.pl` and blocks builds on current `ERROR`-level findings while still printing the remaining warning backlog.
- Linux hosts use `format_neurolink_c_style.sh` and `check_neurolink_linux_c_style.sh` as the canonical style entrypoints.
- To auto-fix style drift:

```powershell
(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression
conda activate zephyr
pwsh applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -Fix
```

- To run the Linux-style lint gate directly:

```powershell
(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression
conda activate zephyr
pwsh applocation/NeuroLink/scripts/check_neurolink_linux_c_style.ps1
```

- Style gate follows Linux-kernel-like rules (`tab=8`, Linux brace style, 80-column limit) via `neuro_unit/.clang-format`.
- Local Windows execution prefers native `perl` when present and otherwise falls back to WSL for `checkpatch.pl`.
- If the repository was copied from Windows to Linux, preview or clear lingering Zone.Identifier files before builds:

```bash
bash applocation/NeuroLink/scripts/clean_zone_identifier.sh
bash applocation/NeuroLink/scripts/clean_zone_identifier.sh --execute
```

生成的扩展位于：

- `build/neurolink_unit/llext/neuro_unit_app.llext`

## Operation Guide

测试、构建、WSL 运行与证据路径统一见：`applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
主机部署规范、Linux/Windows 脚本分层和依赖约束见：`applocation/NeuroLink/docs/project/DEPLOYMENT_STANDARD.md`
release-1.1.0 实板 Linux 接入、WSL zenoh router 与 Linux smoke 执行步骤见：`applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md`

实板 smoke 入口：

- Linux UART monitor helper: `bash applocation/NeuroLink/scripts/monitor_neurolink_uart.sh --device /dev/ttyACM0`
- Linux UART capture helper: `python3 applocation/NeuroLink/scripts/capture_neurolink_uart.py --device /dev/ttyACM0`
- Linux router/board preflight helper: `bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --auto-start-router`
- Board-bound WSL recovery helper for `dnesp32s3b`: `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --wifi-ssid <ssid> --wifi-credential <credential>`
- Linux canonical helper: `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`
- Linux canonical helper with tracked dependency install: `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps`
- WSL router install helper: `bash applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh`
- WSL router run helper: `bash applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh`

Smoke helper依赖 `core_cli.py` 的 Python `zenoh` 模块；若当前 `.venv` 缺失该模块，先执行：

```bash
python3 -m pip install -r applocation/NeuroLink/subprojects/unit_cli/requirements.txt
```

或者直接通过 bootstrap/smoke 入口自动安装：

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps
bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --auto-start-router
bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps
```

当前 smoke helper 默认会先执行 preflight，并且会把 reply payload 中的 `status=error` 视为失败，而不是只看 `core_cli.py` 的进程退出码。

## Runtime Notes

- Port 层已收敛为 `generic` 单实现，统一通过 `neuro_unit_port_init()` 进入。
- 硬件相关能力通过 port filesystem/network ops 表达；默认 `generic` provider 不启用存储/网络能力，调用侧走能力门禁返回 `NOT_SUPPORTED`。
- LLEXT artifact load、Zenoh artifact download、update verify/reconcile 的文件访问通过 port filesystem ops 执行；recovery seed store 保留独立 fs-ops 注入 seam 以维持单元测试隔离。

- 默认 node id 固定为 `unit-01`。
- 默认 zenoh 模式为 `client`，未显式指定 `connect` endpoint 时依赖 scouting/router 默认发现。
- `prepare` 通过 Zenoh query/reply 分块拉取产物到 `/SD:/apps/<app-id>.llext`。
- `verify` 在 `verify_begin()` 之后若出现产物状态更新失败或 `verify_complete` 失败，会显式收敛到 update manager `FAILED`，持久化 recovery seed 快照，并发布 verify error event，避免状态机滞留在 `VERIFYING`。
- release-1.0.2 目标是移除 `prepare --url` 兼容路径，统一为 Zenoh-only。
- `prepare` 与 `activate` 会输出内存快照日志，便于评估系统堆、ESP internal/SPIRAM 堆和关键线程剩余栈空间。
- `activate` 会调用 LLEXT runtime 的 `load + start`。
- Lease 目前是内存态最小实现，覆盖 `app/<app-id>/control`、`app/<app-id>/command/<command-name>` 和 `update/app/<app-id>/activate` 这类核心受保护资源。

## Port Integration Rules

1. Port 层保持 generic-only 单实现，不再新增板卡专用 provider 文件。
2. 板级差异通过配置与上层抽象契约处理，不在 port 目录引入新的 selector 分支。
3. `app_runtime_cmd_set_config()` 仅保留 capability/path/runtime 配置语义；storage/network 命令执行必须通过 port ops，未启用能力必须返回 deterministic `NOT_SUPPORTED`。
4. 新增文件访问调用点优先使用 `neuro_unit_port_get_fs_ops()`，除非模块已有明确的测试注入 seam。
5. 任何能力扩展都需要同步更新 UT 与 `PROJECT_PROGRESS.md` 证据条目。