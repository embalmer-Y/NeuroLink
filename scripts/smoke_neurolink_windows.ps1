param(
    [string]$PythonExe = "D:/Compiler/anaconda/envs/zephyr/python.exe",
    [string]$Node = "unit-01",
    [string]$AppId = "neuro_unit_app",
    [string]$ArtifactFile = "build/neurolink_unit/llext/neuro_unit_app.llext",
    [string]$ActivateLeaseId = "lease-act-017b-001",
    [string]$ActivateLeaseResource = "update/app/neuro_unit_app/activate",
    [int]$LeaseTtlMs = 120000,
    [int]$EventsDurationSec = 20,
    [string]$OutputDir = "applocation/NeuroLink/smoke-evidence"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$evidenceFile = Join-Path $OutputDir "SMOKE-017B-001-$ts.ndjson"

function Invoke-Step {
    param(
        [string]$Step,
        [string[]]$StepArgs
    )

    $cmd = @("applocation/NeuroLink/neuro_cli/src/neuro_cli.py", "--output", "json", "--node", $Node) + $StepArgs
    $output = & $PythonExe @cmd
    $exitCode = $LASTEXITCODE

    [PSCustomObject]@{
        timestamp = (Get-Date).ToString("o")
        step = $Step
        exit_code = $exitCode
        command = @($PythonExe) + $cmd
        output = ($output -join "`n")
    } | ConvertTo-Json -Depth 8 | Out-File -FilePath $evidenceFile -Append -Encoding utf8

    if ($exitCode -ne 0) {
        throw "Step '$Step' failed with exit code $exitCode"
    }
}

Write-Host "[SMOKE-017B] writing evidence to $evidenceFile"

Invoke-Step -Step "query_device" -StepArgs @("query", "device")
Invoke-Step -Step "lease_acquire_activate" -StepArgs @("lease", "acquire", "--resource", $ActivateLeaseResource, "--lease-id", $ActivateLeaseId, "--ttl-ms", "$LeaseTtlMs")
Invoke-Step -Step "deploy_prepare" -StepArgs @("deploy", "prepare", "--app-id", $AppId, "--file", $ArtifactFile)
Invoke-Step -Step "deploy_verify" -StepArgs @("deploy", "verify", "--app-id", $AppId)
Invoke-Step -Step "deploy_activate" -StepArgs @("deploy", "activate", "--app-id", $AppId, "--lease-id", $ActivateLeaseId, "--start-args", "mode=demo,profile=release")
Invoke-Step -Step "monitor_events" -StepArgs @("monitor", "events", "--duration", "$EventsDurationSec")

Write-Host "[SMOKE-017B] PASS"
Write-Host "[SMOKE-017B] evidence: $evidenceFile"

