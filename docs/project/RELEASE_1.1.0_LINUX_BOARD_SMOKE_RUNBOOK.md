# Release 1.1.0 Linux Board Smoke Runbook

## 1. Objective

This runbook defines the executable path for Release 1.1.0 board attach, Linux flash,
WSL-hosted zenoh router startup, and Linux-native real-board smoke evidence.

Linux remains the canonical board build, flash, serial, and smoke host.
WSL Ubuntu is used only as the zenoh router host when the lab machine still routes
developer workflows through a Windows workstation.

## 2. Environment Model

1. Linux host role:
   - build the board image and LLEXT artifact
   - flash `dnesp32s3b/esp32s3/procpu`
   - monitor board serial output
   - run the Linux smoke command sequence
2. WSL Ubuntu role:
   - install `zenohd` from the official Eclipse Zenoh Debian repository
   - listen on a board-reachable endpoint, normally `tcp/0.0.0.0:7447`
3. Board default zenoh endpoint:
   - `CONFIG_NEUROLINK_ZENOH_CONNECT="tcp/192.168.2.95:7447"`
   - file: `applocation/NeuroLink/neuro_unit/boards/dnesp32s3b_esp32s3_procpu.conf`

## 3. WSL USB Attach Gate

If Linux is running inside WSL, the board must be attached to WSL before any flash or
serial step can succeed.

Recommended Windows-side sequence:

```powershell
usbipd list
usbipd bind --busid <BUSID>
usbipd attach --wsl --busid <BUSID>
```

WSL-side verification:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM*
```

Do not continue until a serial device appears in WSL.

For the validated `dnesp32s3b` board path, the formal WSL helper can perform the attach,
UART preparation replay, preflight, and final `query device` verification in one command:

```bash
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh \
   --wifi-ssid <ssid> \
   --wifi-credential <credential>
```

This helper is board-bound to the current CH343-backed `dnesp32s3b` lab setup and should be
preferred over manual `usbipd` plus ad-hoc serial command replay when the target board matches.

## 4. Linux Board Build and Flash

Bootstrap and build:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict
python3 -m pip install -r applocation/NeuroLink/neuro_cli/requirements.txt
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --pristine-always
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ext
```

Equivalent bootstrap-assisted dependency install:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps
```

Expected artifacts:

1. `build/neurolink_unit/zephyr/zephyr.elf`
2. `build/neurolink_unit/llext/neuro_unit_app.llext`

Flash the board once the device path is known:

```bash
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset flash-unit --esp-device /dev/ttyUSB0
```

## 5. Linux Serial Readiness Gate

Zephyr board guidance for ESP32 boards supports a serial monitor after flash.
In the current NeuroLink Linux/WSL environment, the validated serial monitor method is
pyserial `miniterm`, wrapped by `applocation/NeuroLink/scripts/monitor_neurolink_uart.sh`.

Preferred command:

```bash
bash applocation/NeuroLink/scripts/monitor_neurolink_uart.sh --device /dev/ttyACM0
```

Direct equivalent:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict
python3 -m serial.tools.miniterm /dev/ttyACM0 115200 --eol LF
```

Notes:

1. Exit `miniterm` with `Ctrl+]`.
2. The wrapper automatically captures a timestamped serial log under `smoke-evidence/serial-diag/`.
3. `west espressif monitor` remains a Zephyr/Espressif-style option, but `miniterm` is the currently validated tool in this workspace.

For non-interactive evidence capture, use the formal Python helper consolidated from the
earlier ad-hoc root-level probe scripts:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict
python3 applocation/NeuroLink/scripts/capture_neurolink_uart.py \
   --device /dev/ttyACM0 \
   --send-after '6:app mount_storage' \
   --send-after '10:app network_connect <ssid> <credential>'
```

This helper writes a timestamped log under `applocation/NeuroLink/smoke-evidence/serial-diag/`
and can automatically wake the shell plus send `app status` when the prompt appears.

Board-side preparation sequence:

1. `app mount_storage`
2. `app network_connect <ssid> <credential>`

Required ready-state evidence in serial log:

1. `storage mounted`
2. `network ready`
3. `opening zenoh session`
4. `tcp probe succeeded`
5. `NeuroLink zenoh queryables ready`

Reference evidence:

1. `applocation/NeuroLink/smoke-evidence/serial-diag/serial-network-retry-20260415-020239.log`
2. `applocation/NeuroLink/smoke-evidence/serial-diag/miniterm-20260419T063813Z.log`

## 6. WSL Ubuntu Zenoh Router Install and Run

Install the router in WSL Ubuntu:

```bash
bash applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh
```

If `sudo` is unavailable or policy requires user-local install only:

```bash
bash applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh --mode user-local
export PATH="$HOME/.local/bin:$PATH"
```

Run the router in the foreground:

```bash
bash applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh --listen tcp/0.0.0.0:7447
```

If the router should run without the REST interface, use:

```bash
bash applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh --listen tcp/0.0.0.0:7447 --rest-http-port none
```

Operational check:

1. If board serial logs revert to `tcp probe connect failed` after a previously successful smoke run, verify `zenohd` is still alive before changing firmware or firewall rules.
2. WSL-side quick check: `ss -ltnp | grep 7447`
3. If nothing is listening on `7447`, restart the router first:

```bash
bash applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh --listen tcp/0.0.0.0:7447 --rest-http-port none --background
```

## 7. Router Reachability Decision

The board must be able to reach the router endpoint that NeuroLink is configured to use.

1. If `tcp/192.168.2.95:7447` is still valid in the active lab environment, keep the
   board configuration unchanged.
2. If the router is reachable through a different address, do not rely on WSL NAT guesswork.
   Rebuild the board with an explicit `CONFIG_NEUROLINK_ZENOH_CONNECT` override or expose
   the router on a board-reachable address.
3. Use the board serial gate, not host assumption, as the source of truth.
4. If the board reaches `network ready` but repeated `tcp probe connect failed` occurs while `zenohd` is running inside WSL, treat Windows firewall/UAC policy as the first suspect before changing board firmware.
5. If `neuro_cli.py query device` returns `no_reply` and board serial simultaneously shows `tcp probe connect failed`, verify both the Windows firewall profile and that `zenohd` is still listening on `7447`; router process exit produces the same board-side symptom as a blocked ingress path.

### 7.1 Windows Inbound Allow Rule for WSL-hosted `zenohd`

When WSL uses mirrored/bridged networking and exposes the same LAN IPv4 as the Windows host,
the board connects to the Windows host address even though `zenohd` runs inside WSL. In that
model, Windows inbound policy must allow TCP `7447`.

Required facts for the current validated lab state:

1. board endpoint: `tcp/192.168.2.95:7447`
2. WSL interface: `eth2` on `192.168.2.95/24`
3. router listener: `0.0.0.0:7447`

Recommended Windows administrator command:

```powershell
New-NetFirewallRule \
   -DisplayName "NeuroLink zenohd 7447" \
   -Direction Inbound \
   -Action Allow \
   -Protocol TCP \
   -LocalPort 7447 \
   -Profile Private
```

If the active Ethernet profile is not `Private`, either change the network profile first or
temporarily widen the rule:

```powershell
New-NetFirewallRule \
   -DisplayName "NeuroLink zenohd 7447 AnyProfile" \
   -Direction Inbound \
   -Action Allow \
   -Protocol TCP \
   -LocalPort 7447 \
   -Profile Any
```

Verification from an elevated PowerShell session:

```powershell
Get-NetFirewallRule -DisplayName "NeuroLink zenohd 7447*" |
   Select-Object DisplayName, Enabled, Direction, Action
```

Important:

1. These commands require an elevated Windows PowerShell or Windows Terminal session.
2. Running them through a non-elevated `powershell.exe` inside WSL will fail with `Windows System Error 5`.
3. Do not proceed to Linux smoke until board serial output changes from `tcp probe connect failed` to `tcp probe succeeded`.

## 8. Linux Native Smoke Execution

Before starting smoke, run the Linux preflight helper so router state, artifact presence,
serial visibility, and `query device` reachability are classified explicitly:

```bash
bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --auto-start-router
```

If the lab procedure requires a hard failure when no serial device is visible in Linux, use:

```bash
bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --auto-start-router --require-serial
```

Once the board reaches queryable-ready state, run the Linux-native smoke helper:

```bash
bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh
```

This smoke helper now runs `preflight_neurolink_linux.sh` automatically before the deploy
sequence. Use `--skip-preflight` only when troubleshooting the smoke helper itself rather than
board/router readiness.

If the active `.venv` may still be missing tracked Neuro CLI Python packages, the
smoke helper can install them before starting:

```bash
bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps
```

Important result contract:

1. A smoke step is successful only when the CLI command exits successfully and the JSON reply payload does not report `status=error`.
2. Protocol-level error replies such as `deploy_activate -> status=error` are now treated as smoke failures even if `neuro_cli.py` itself exits `0`.
3. Latest validated operator automation on the active lab host used `bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --wifi-ssid cemetery --wifi-credential goodluck1024 --capture-duration-sec 20`, which restored the board, verified `board=dnesp32s3b`, and left the node queryable from Linux.
4. The `deploy_activate` regression caused by reloading an already running `neuro_unit_app` has been fixed in `handle_update_activate()`: the runtime now unloads an existing instance before loading the prepared artifact.
5. Latest validated smoke replay after this fix is PASS; use `SMOKE-017B-LINUX-001-20260421-165505.*` as the current truth for the active Linux/WSL board path.

This script mirrors the current `applocation/NeuroLink/scripts/smoke_neurolink_windows.ps1` command sequence:

1. `query_device`
2. lease acquire for activate resource
3. `deploy prepare`
4. `deploy verify`
5. `deploy activate`
6. event monitoring

Evidence output:

1. `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-<timestamp>.ndjson`
2. `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-<timestamp>.summary.txt`

Preflight output classification:

1. `ready`: router is listening and `query device` succeeded.
2. `router_not_listening`: start or restart `zenohd` before retrying.
3. `serial_device_missing`: no `/dev/ttyACM*` or `/dev/ttyUSB*` is visible when `--require-serial` is requested.
4. `no_reply_board_not_attached`: router is healthy but the board is not exposed to Linux.
5. `no_reply_board_unreachable`: router is healthy and a serial device exists, but the node still is not replying.

Dependency note:

1. `neuro_cli.py` imports the Python module `zenoh`, provided by `eclipse-zenoh`.
2. The tracked install source is `applocation/NeuroLink/neuro_cli/requirements.txt`.
3. The canonical bootstrap script can install those tracked packages directly with `source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps`.
4. If the smoke helper reports a missing `zenoh` module, either install it with `python3 -m pip install -r applocation/NeuroLink/neuro_cli/requirements.txt` inside the active `.venv` or rerun smoke with `--install-missing-cli-deps`.

## 9. Release Ledger Update Gate

After successful execution, append the following to `PROJECT_PROGRESS.md`:

1. Linux host device attach result
2. flash command and device path used
3. serial readiness evidence path
4. WSL zenoh router install/start command and endpoint choice
5. smoke evidence path and outcome
