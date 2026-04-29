# Neuro CLI Windows Setup Reference

This is the canonical Windows zero-host setup reference for the Neuro CLI skill.
Windows is supported as a PowerShell-first compatibility host, with WSL used
where the validated router, USB serial, or Linux-canonical evidence workflow
requires it.

Agents must treat installer prompts, administrator elevation, execution policy,
USB drivers, and USB/IP passthrough as operator-approved steps. Prefer
`workflow plan setup-windows` for the machine-readable command list before
executing anything.

## Supported Host Shape

1. Windows 10/11 with PowerShell 7 or Windows PowerShell.
2. Network access for installers, Python packages, and west modules.
3. A workspace root containing `zephyr`, `modules`, and `applocation/NeuroLink`.
4. Python 3.12 or compatible Python with `venv` support.
5. Zephyr SDK installed or installable by the operator.

WSL is not required for local parser, wrapper, and documentation checks. Use WSL
for USB/IP attach, router/serial workflows, or final Linux-canonical hardware
evidence when native Windows serial/router behavior is not the validated path.

## Workflow Plan

```powershell
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan setup-windows
```

The plan is non-executing JSON. Review `preconditions`, `commands`,
`expected_success`, and `failure_statuses` before running commands manually.

## Tool Acquisition

Operator-approved `winget` examples:

```powershell
winget install --id Git.Git -e --source winget
winget install --id Python.Python.3.12 -e --source winget
winget install --id Kitware.CMake -e --source winget
winget install --id Ninja-build.Ninja -e --source winget
winget install --id Microsoft.PowerShell -e --source winget
```

If `winget` is unavailable or blocked by policy, use the equivalent enterprise
package manager or manual installers and then rerun strict validation.

## Workspace And Python Environment

From the west workspace root:

```powershell
py -3 -m venv .venv
. .venv/Scripts/Activate.ps1
python -m pip install --upgrade pip wheel west
python -m pip install -r zephyr/scripts/requirements.txt -r applocation/NeuroLink/neuro_cli/requirements.txt
west update
```

If PowerShell blocks `.venv` activation, request operator approval for a
process-scoped policy change such as:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Do not silently change machine-wide execution policy.

## Zephyr SDK

Read the required SDK version from the workspace:

```powershell
Get-Content zephyr/SDK_VERSION
```

For this workspace the current value is `1.0.1`. Install the matching Zephyr SDK
as an operator step, then point the environment at it. A conventional install
location is:

```powershell
$env:ZEPHYR_SDK_INSTALL_DIR = "$HOME/zephyr-sdk-$(Get-Content zephyr/SDK_VERSION)"
```

If the SDK is installed elsewhere, set `ZEPHYR_SDK_INSTALL_DIR` to the real path
before strict validation. Do not continue to Unit build commands while the path
is unset or lacks `cmake/Zephyr-sdkConfig.cmake`.

## Current Supported Checks

```powershell
. applocation/NeuroLink/scripts/setup_neurolink_env.ps1 -Strict
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities
```

The compatibility conda activation path remains available when the operator has
created a conda environment:

```powershell
. applocation/NeuroLink/scripts/setup_neurolink_env.ps1 -Activate -CondaEnv zephyr -Strict
```

## Build And Test Checks

Ask the CLI for exact commands before running builds or board checks:

```powershell
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-build
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan cli-tests
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan app-build
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan memory-evidence
```

For hardware work, check whether the validated path requires WSL USB/IP or
native Windows serial access before continuing:

```powershell
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan smoke
```

## WSL Boundary

Use native PowerShell for environment validation, parser checks, CLI wrapper
JSON checks, and documentation workflows. Use WSL when the workflow requires the
Linux router/serial path, USB/IP device attach, or Linux-canonical evidence.
Do not treat a native Windows setup check as hardware closure evidence unless a
later closure slice explicitly validates that path.

## Failure Recovery

1. `missing required command`: install the named tool and rerun
   `setup_neurolink_env.ps1 -Strict`.
2. `execution_policy_blocked`: request operator approval for a process-scoped
   execution policy change, then reactivate `.venv`.
3. `python_dependency_missing`: activate `.venv` and install Zephyr plus Neuro
   CLI requirements.
4. Zephyr SDK missing: install the SDK or set `ZEPHYR_SDK_INSTALL_DIR`.
5. `perl-or-wsl` missing: install Perl or enable WSL before style/build gates
   that require it.
6. USB/serial unavailable: install drivers, attach the device to WSL with
   USB/IP, or switch to a Linux host before board workflows.
