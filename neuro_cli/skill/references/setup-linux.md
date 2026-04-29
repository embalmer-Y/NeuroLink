# Neuro CLI Linux Setup Reference

This is the canonical Linux zero-host setup reference for the Neuro CLI skill.
It assumes a fresh Linux host with network access and a west workspace that will
contain `zephyr`, `modules`, and `applocation/NeuroLink`.

Agents must treat package installation, group membership, USB permissions, and
SDK installer prompts as operator-approved steps. Prefer `workflow plan
setup-linux` for the machine-readable command list before executing anything.

## Supported Host Shape

1. Ubuntu/Debian-style package manager for the concrete package command below.
2. Bash shell with network access.
3. A workspace root equivalent to `/home/emb/project/zephyrproject` containing
   `applocation/NeuroLink`.
4. Python 3 with `venv` support.
5. Zephyr SDK installed or installable by the operator.

For non-Debian distributions, map the package names to the host package manager
and keep the validation commands unchanged.

## Workflow Plan

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan setup-linux
```

The plan is non-executing JSON. Review `preconditions`, `commands`,
`expected_success`, and `failure_statuses` before running commands manually.

## System Packages

Operator-approved package installation for Ubuntu/Debian hosts:

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip cmake ninja-build gperf ccache dfu-util device-tree-compiler wget curl xz-utils file make gcc gcc-multilib g++-multilib libsdl2-dev libmagic1 clang-format perl usbutils
```

If `west`, `cmake`, `ninja`, `clang-format`, or `perl` is missing later, rerun
the package step or install the distribution-specific equivalent.

## Workspace And Python Environment

From the west workspace root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip wheel west
python3 -m pip install -r zephyr/scripts/requirements.txt -r applocation/NeuroLink/neuro_cli/requirements.txt
```

If the workspace was freshly cloned or unpacked, initialize/update modules before
building:

```bash
west update
```

The `zenoh-pico` module is required by the Unit build path. If a build reports a
missing Zenoh module, rerun `west update` from the workspace root and verify the
module exists under the west-managed module tree.

## Zephyr SDK

Read the required SDK version from the workspace instead of guessing:

```bash
cat zephyr/SDK_VERSION
```

For this workspace the current value is `1.0.1`. Install the matching Zephyr SDK
as an operator step, then point the environment at it. A conventional install
location is:

```bash
export ZEPHYR_SDK_INSTALL_DIR=${HOME}/zephyr-sdk-$(cat zephyr/SDK_VERSION)
```

The environment validation script also auto-detects SDK directories matching
`$HOME/zephyr-sdk-*` or `/opt/zephyr-sdk-*`. If the SDK is installed elsewhere,
export the real path explicitly before strict validation:

```bash
export ZEPHYR_SDK_INSTALL_DIR=/path/to/zephyr-sdk
```

If no SDK is installed, download the matching Zephyr SDK release for the host,
unpack or run its installer, and rerun strict validation. Do not continue to
Unit build commands while `ZEPHYR_SDK_INSTALL_DIR` is unset or points to a
directory without `cmake/Zephyr-sdkConfig.cmake`.

## Current Supported Checks

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-neuro-cli-deps
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities
```

## Build And Test Checks

Ask the CLI for exact commands before running builds or board checks:

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-build
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-tests
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan cli-tests
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan app-build
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan memory-evidence
```

For hardware work, require explicit serial visibility and router readiness:

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan smoke
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan callback-smoke
```

## USB And Serial Permissions

Hardware preflight requires the Unit serial device to be visible to the Linux
host. Operator steps may include adding the user to `dialout`, installing udev
rules, reconnecting USB, or attaching USB devices into WSL. Do not continue to
deploy/control workflows while preflight reports `serial_device_missing`.

## Failure Recovery

1. `missing required command`: install the named package and rerun
   `setup_neurolink_env.sh --strict`.
2. `python module 'zenoh' missing`: activate `.venv` and install
   `applocation/NeuroLink/neuro_cli/requirements.txt`.
3. Zephyr SDK missing: install the SDK or export `ZEPHYR_SDK_INSTALL_DIR`.
4. `zenoh-pico` or other module missing: rerun `west update`.
5. `serial_device_missing`: fix host USB enumeration, permissions, or WSL USB
   attach before board workflows.
6. `no_reply_board_unreachable`: host serial/router may be up, but the Unit is
   not replying; check board network readiness and UART logs.
