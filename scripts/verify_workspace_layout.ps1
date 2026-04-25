param(
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $repoRoot

$violations = @()

$violations += Get-ChildItem -Path $repoRoot -Directory -Filter "build_*" -ErrorAction SilentlyContinue
$violations += Get-ChildItem -Path $repoRoot -Directory -Filter "twister-out*" -ErrorAction SilentlyContinue

if ($violations.Count -eq 0) {
    Write-Host "layout check passed: no root-level build_* or twister-out* directories found"
    exit 0
}

Write-Host "layout check found forbidden generated directories:" -ForegroundColor Yellow
$violations | Sort-Object -Property Name | ForEach-Object {
    Write-Host " - $($_.Name)"
}

if ($Strict) {
    exit 1
}

exit 0
