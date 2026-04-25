param(
    [string[]]$Targets = @(
        "applocation/NeuroLink/neuro_unit/include",
        "applocation/NeuroLink/neuro_unit/src",
        "applocation/NeuroLink/neuro_unit/tests/unit/src"
    ),
    [string[]]$IgnoreTypes = @(
        "SPDX_LICENSE_TAG"
    ),
    [switch]$FailOnWarnings
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Get-TargetFiles {
    param([string[]]$RootTargets)

    $collected = @()
    foreach ($target in $RootTargets) {
        if (-not (Test-Path $target)) {
            continue
        }

        $collected += Get-ChildItem -Path $target -Recurse -File |
            Where-Object { $_.Extension -in ".c", ".h" }
    }

    return $collected | Sort-Object -Property FullName -Unique
}

function Get-WslPath {
    param([string]$WindowsPath)

    $normalized = $WindowsPath.Replace('\', '/')
    if ($normalized -match '^([A-Za-z]):/(.*)$') {
        return "/mnt/$($matches[1].ToLower())/$($matches[2])"
    }

    throw "cannot convert Windows path to WSL path: $WindowsPath"
}

function Invoke-CheckpatchNative {
    param(
        [string]$RepoRoot,
        [string[]]$RelativeFiles,
        [string[]]$TypesToIgnore
    )

    $scriptPath = Join-Path $RepoRoot "zephyr/scripts/checkpatch.pl"
    $output = @()
    foreach ($file in $RelativeFiles) {
        $args = @($scriptPath, "--no-tree", "--terse", "--show-types")
        foreach ($type in $TypesToIgnore) {
            $args += @("--ignore", $type)
        }
        $args += @("--file", $file)

        $result = & perl @args 2>&1
        if ($result) {
            $output += $result
        }
    }

    return ,$output
}

function Invoke-CheckpatchWsl {
    param(
        [string]$RepoRoot,
        [string[]]$RelativeFiles,
        [string[]]$TypesToIgnore
    )

    $repoRootWsl = Get-WslPath -WindowsPath $RepoRoot
    $ignoreArgs = ($TypesToIgnore | ForEach-Object { "--ignore $_" }) -join ' '
    $output = @()
    foreach ($file in $RelativeFiles) {
        $command = "cd '$repoRootWsl' && perl zephyr/scripts/checkpatch.pl --no-tree --terse --show-types $ignoreArgs --file '$file'"
        $result = & wsl bash -lc $command 2>&1
        if ($result) {
            $output += $result
        }
    }

    return ,$output
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

& pwsh -File "applocation/NeuroLink/scripts/format_neurolink_c_style.ps1" -CheckOnly
if ($LASTEXITCODE -ne 0) {
    throw "clang-format check failed. Run format_neurolink_c_style.ps1 -Fix and retry."
}

$files = Get-TargetFiles -RootTargets $Targets
if ($files.Count -eq 0) {
    Write-Host "no C/H files found under target paths"
    exit 0
}

$relativeFiles = $files | ForEach-Object {
    $_.FullName.Substring($repoRoot.Length + 1).Replace('\', '/')
}

$checkpatchOutput = @()
if (Get-Command perl -ErrorAction SilentlyContinue) {
    $checkpatchOutput = Invoke-CheckpatchNative -RepoRoot $repoRoot -RelativeFiles $relativeFiles -TypesToIgnore $IgnoreTypes
} elseif (Get-Command wsl -ErrorAction SilentlyContinue) {
    $checkpatchOutput = Invoke-CheckpatchWsl -RepoRoot $repoRoot -RelativeFiles $relativeFiles -TypesToIgnore $IgnoreTypes
} else {
    throw "Neither perl nor WSL is available. Install Perl or enable WSL to run zephyr/scripts/checkpatch.pl."
}

$checkpatchOutput = @($checkpatchOutput | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

$checkpatchFindings = @($checkpatchOutput | Where-Object {
    $_ -match ': (ERROR|WARNING):[A-Z0-9_]+'
})
$errorCount = @($checkpatchFindings | Where-Object { $_ -match ': ERROR:' }).Count
$warningCount = @($checkpatchFindings | Where-Object { $_ -match ': WARNING:' }).Count

if ($checkpatchFindings.Count -eq 0) {
    Write-Host "linux kernel style check passed ($($files.Count) files)"
    exit 0
}

Write-Host "linux kernel style findings: errors=$errorCount warnings=$warningCount" -ForegroundColor Yellow
$checkpatchOutput | ForEach-Object { Write-Host $_ }

if ($errorCount -gt 0 -or ($FailOnWarnings -and $warningCount -gt 0)) {
    exit 1
}

exit 0
