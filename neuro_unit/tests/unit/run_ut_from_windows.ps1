param(
    [string]$Distro = ""
)

$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
$scriptDir = Split-Path -Parent $scriptPath
$repoRoot = Resolve-Path (Join-Path $scriptDir "../../../../..")
$linuxScript = Join-Path $scriptDir "run_ut_linux.sh"

function Convert-ToWslPath {
    param([string]$WindowsPath)

    $normalized = $WindowsPath -replace '\\', '/'
    if ($normalized -match '^([A-Za-z]):/(.*)$') {
        $drive = $matches[1].ToLowerInvariant()
        $rest = $matches[2]
        return "/mnt/$drive/$rest"
    }

    return $normalized
}

$distroList = @(wsl -l -q 2>$null)
if ($distroList.Count -eq 0) {
    Write-Host "No WSL distro installed. Install one first, then rerun this script." 
    exit 2
}

$selectedDistro = if ([string]::IsNullOrWhiteSpace($Distro)) {
    $distroList[0].Trim()
} else {
    $Distro
}

$repoRootPath = $repoRoot.ProviderPath
$repoRootWsl = Convert-ToWslPath -WindowsPath $repoRootPath
$linuxScriptWsl = Convert-ToWslPath -WindowsPath $linuxScript

wsl -d $selectedDistro bash -lc "cd '$repoRootWsl' && bash '$linuxScriptWsl' '$repoRootWsl'"
exit $LASTEXITCODE
