param(
    [switch]$Execute,
    [switch]$IncludeEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $repoRoot

$targets = @()
$targets += Get-ChildItem -Path $repoRoot -Directory -Filter "build_*" -ErrorAction SilentlyContinue
$targets += Get-ChildItem -Path $repoRoot -Directory -Filter "twister-out*" -ErrorAction SilentlyContinue

if ($IncludeEvidence) {
    $evidenceDir = Join-Path $repoRoot "applocation/NeuroLink/smoke-evidence"
    if (Test-Path $evidenceDir) {
        $targets += Get-ChildItem -Path $evidenceDir -Directory -ErrorAction SilentlyContinue
    }
}

$targets = $targets | Sort-Object -Property FullName -Unique

if ($targets.Count -eq 0) {
    Write-Host "no generated output directories matched cleanup rules"
    exit 0
}

Write-Host "cleanup candidates:" -ForegroundColor Yellow
$targets | ForEach-Object {
    Write-Host " - $($_.FullName)"
}

if (-not $Execute) {
    Write-Host "preview only. re-run with -Execute to delete." -ForegroundColor Cyan
    exit 0
}

$targets | ForEach-Object {
    Remove-Item -Path $_.FullName -Recurse -Force
    Write-Host "removed $($_.FullName)"
}

Write-Host "cleanup completed"
