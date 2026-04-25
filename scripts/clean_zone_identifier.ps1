param(
    [switch]$Execute,
    [string]$TargetRoot = "applocation/NeuroLink"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$literalCandidates = @(
    Get-ChildItem -Path $TargetRoot -Filter "*:Zone.Identifier" -Recurse -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            [PSCustomObject]@{
                Kind = "literal-file"
                DisplayPath = $_.FullName
                Path = $_.FullName
                Stream = $null
            }
        }
)

$streamCandidates = @()
$streamParameterAvailable = (Get-Command Get-Item).Parameters.ContainsKey("Stream")
if ($streamParameterAvailable) {
    $baseFiles = @(Get-ChildItem -Path $TargetRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike "*:Zone.Identifier" })

    foreach ($file in $baseFiles) {
        try {
            $streams = @(Get-Item -LiteralPath $file.FullName -Stream Zone.Identifier -ErrorAction Stop)
        } catch {
            continue
        }

        foreach ($stream in $streams) {
            $streamCandidates += [PSCustomObject]@{
                Kind = "ads-stream"
                DisplayPath = "$($file.FullName):$($stream.Stream)"
                Path = $file.FullName
                Stream = $stream.Stream
            }
        }
    }
}

$candidates = @($literalCandidates + $streamCandidates | Sort-Object -Property DisplayPath -Unique)
if ($candidates.Count -eq 0) {
    Write-Host "no matches found for Zone.Identifier under $TargetRoot"
    exit 0
}

Write-Host "zone identifier candidates: $($candidates.Count)" -ForegroundColor Yellow
$candidates | ForEach-Object {
    Write-Host " - $($_.DisplayPath)"
}

if (-not $Execute) {
    Write-Host "preview only. re-run with -Execute to delete." -ForegroundColor Cyan
    exit 0
}

foreach ($candidate in $candidates) {
    if ($candidate.Kind -eq "literal-file") {
        Remove-Item -LiteralPath $candidate.Path -Force
    } else {
        Remove-Item -LiteralPath $candidate.Path -Stream $candidate.Stream -Force
    }

    Write-Host "removed $($candidate.DisplayPath)"
}

Write-Host "zone identifier cleanup completed"
