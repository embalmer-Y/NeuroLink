param(
    [switch]$Activate,
    [switch]$Strict,
    [string]$CondaEnv = "zephyr"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Resolve-CommandName {
    param([string[]]$Candidates)

    foreach ($candidate in $Candidates) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }

    return $null
}

function Enter-ZephyrConda {
    param([string]$EnvironmentName)

    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
        throw "conda command not found. Install or initialize conda before using -Activate."
    }

    (& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression
    conda activate $EnvironmentName
}

function Get-ZephyrSdkDir {
    if ($env:ZEPHYR_SDK_INSTALL_DIR -and (Test-Path (Join-Path $env:ZEPHYR_SDK_INSTALL_DIR "cmake/Zephyr-sdkConfig.cmake"))) {
        return $env:ZEPHYR_SDK_INSTALL_DIR
    }

    $candidates = @()
    $searchRoots = @($HOME, "C:\", "D:\")
    foreach ($root in $searchRoots) {
        if (-not $root -or -not (Test-Path $root)) {
            continue
        }

        $candidates += Get-ChildItem -Path $root -Directory -Filter "zephyr-sdk-*" -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "cmake/Zephyr-sdkConfig.cmake") }
    }

    $latest = $candidates | Sort-Object -Property FullName | Select-Object -Last 1
    if ($latest) {
        return $latest.FullName
    }

    return $null
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

if ($Activate) {
    Enter-ZephyrConda -EnvironmentName $CondaEnv
}

if (-not $env:ZEPHYR_BASE) {
    $zephyrBase = Join-Path $repoRoot "zephyr"
    if (Test-Path $zephyrBase) {
        $env:ZEPHYR_BASE = $zephyrBase
    }
}

if (-not $env:ZEPHYR_SDK_INSTALL_DIR) {
    $sdkDir = Get-ZephyrSdkDir
    if ($sdkDir) {
        $env:ZEPHYR_SDK_INSTALL_DIR = $sdkDir
    }
}

$warnings = @()
$missingRequired = @()
$missingOptional = @()

$requiredToolGroups = @(
    @{ Label = "python"; Candidates = @("python", "py") },
    @{ Label = "cmake"; Candidates = @("cmake") },
    @{ Label = "ninja"; Candidates = @("ninja") },
    @{ Label = "west"; Candidates = @("west") },
    @{ Label = "clang-format"; Candidates = @("clang-format") }
)

foreach ($toolGroup in $requiredToolGroups) {
    if (-not (Resolve-CommandName -Candidates $toolGroup.Candidates)) {
        $missingRequired += $toolGroup.Label
    }
}

$perlCommand = Resolve-CommandName -Candidates @("perl")
$wslCommand = Resolve-CommandName -Candidates @("wsl")
if (-not $perlCommand -and -not $wslCommand) {
    $missingRequired += "perl-or-wsl"
}

if (-not (Resolve-CommandName -Candidates @("gcovr"))) {
    $missingOptional += "gcovr"
}
if (-not (Resolve-CommandName -Candidates @("qemu-system-x86_64", "qemu-system-i386"))) {
    $missingOptional += "qemu-system-x86"
}
if (-not $env:ZEPHYR_SDK_INSTALL_DIR) {
    $warnings += "Zephyr SDK not auto-detected; set ZEPHYR_SDK_INSTALL_DIR if board builds require it"
}

Write-Host "repo_root=$repoRoot"
Write-Host "conda_env=$CondaEnv"
Write-Host "zephyr_base=$($env:ZEPHYR_BASE ? $env:ZEPHYR_BASE : 'unset')"
Write-Host "zephyr_sdk_install_dir=$($env:ZEPHYR_SDK_INSTALL_DIR ? $env:ZEPHYR_SDK_INSTALL_DIR : 'unset')"
Write-Host "style_gate_provider=$($perlCommand ? 'perl' : ($wslCommand ? 'wsl' : 'missing'))"

if ($warnings.Count -gt 0) {
    $warnings | ForEach-Object { Write-Host "warning: $_" -ForegroundColor Yellow }
}

if ($missingRequired.Count -gt 0) {
    $missingRequired | ForEach-Object { Write-Host "missing required command: $_" -ForegroundColor Red }
    exit 1
}

if ($missingOptional.Count -gt 0) {
    $missingOptional | ForEach-Object { Write-Host "missing optional command: $_" -ForegroundColor Yellow }
}

if ($Strict -and $missingOptional.Count -gt 0) {
    Write-Host "strict mode validated required build tools; optional capabilities remain unavailable" -ForegroundColor Yellow
}

if ($Activate) {
    Write-Host "environment activation completed for the current PowerShell session" -ForegroundColor Green
}
