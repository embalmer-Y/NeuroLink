param(
    [switch]$Fix,
    [switch]$CheckOnly,
    [string[]]$Targets = @(
        "applocation/NeuroLink/neuro_unit/include",
        "applocation/NeuroLink/neuro_unit/src",
        "applocation/NeuroLink/neuro_unit/tests/unit/src"
    )
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Set-LfLineEndings {
    param([string]$Path)

    $content = [System.IO.File]::ReadAllText($Path)
    $normalized = $content.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $normalized.EndsWith("`n")) {
        $normalized += "`n"
    }
    if ($content -cne $normalized) {
        [System.IO.File]::WriteAllText($Path, $normalized, [System.Text.UTF8Encoding]::new($false))
    }
}

if ($Fix -and $CheckOnly) {
    throw "Use either -Fix or -CheckOnly, not both."
}

if (-not $Fix -and -not $CheckOnly) {
    $CheckOnly = $true
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $repoRoot

$clangFormat = Get-Command clang-format -ErrorAction SilentlyContinue
if (-not $clangFormat) {
    throw "clang-format not found in PATH. Activate the zephyr conda environment first."
}

$styleFile = Join-Path $repoRoot "applocation/NeuroLink/neuro_unit/.clang-format"
if (-not (Test-Path $styleFile)) {
    throw "style file not found: $styleFile"
}

$files = @()
foreach ($target in $Targets) {
    if (-not (Test-Path $target)) {
        continue
    }

    $files += Get-ChildItem -Path $target -Recurse -File |
        Where-Object { $_.Extension -in ".c", ".h" }
}

$files = $files | Sort-Object -Property FullName -Unique
if ($files.Count -eq 0) {
    Write-Host "no C/H files found under target paths"
    exit 0
}

if ($Fix) {
    foreach ($file in $files) {
        Set-LfLineEndings -Path $file.FullName
        & $clangFormat.Source -style=file -i $file.FullName
    }
    Write-Host "formatted $($files.Count) files with Linux kernel style and normalized LF line endings"
    exit 0
}

$violations = @()
foreach ($file in $files) {
    & $clangFormat.Source -style=file --dry-run --Werror $file.FullName 2>$null
    if ($LASTEXITCODE -ne 0) {
        $violations += $file.FullName
    }
}

if ($violations.Count -eq 0) {
    Write-Host "c-style check passed ($($files.Count) files)"
    exit 0
}

Write-Host "c-style check failed: $($violations.Count) file(s) need formatting" -ForegroundColor Yellow
$violations | ForEach-Object { Write-Host " - $_" }
exit 1
