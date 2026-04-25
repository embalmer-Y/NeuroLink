param(
    [ValidateSet("unit", "unit-ut", "unit-edk", "unit-app", "unit-ext", "flash-unit")]
    [string]$Preset = "unit",
    [string]$Board = "dnesp32s3b/esp32s3/procpu",
    [string]$BuildDir,
    [switch]$PristineAlways,
    [string]$EspDevice,
    [bool]$CheckCStyle = $true,
    [string[]]$ExtraWestArgs = @(),
    [string[]]$ExtraCmakeArgs = @()
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$envScript = Join-Path $PSScriptRoot "setup_neurolink_env.ps1"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Assert-BuildDir {
    param([string]$Candidate)

    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        throw "build dir is required"
    }

    $normalized = $Candidate.Replace('\\', '/').Trim()
    if ($normalized -notmatch '^build/.+') {
        throw "invalid build dir '$Candidate': only build/<target> is allowed"
    }
    if ($normalized -match '^build_') {
        throw "invalid build dir '$Candidate': root-level build_* is forbidden"
    }
    if ($normalized -match '\.\.') {
        throw "invalid build dir '$Candidate': parent traversal is not allowed"
    }
}

function Assert-ZenohPicoModule {
    if (-not (Test-Path $zenohPicoModuleFile)) {
        throw "missing zenoh-pico Zephyr module at '$zenohPicoModuleFile'. Run 'west update zenoh-pico' or 'west update' after keeping zephyr/submanifests/zenoh-pico.yaml in the workspace."
    }
}

function Get-UnitAppBuildDir {
    $parent = Split-Path $BuildDir -Parent
    $name = Split-Path $BuildDir -Leaf
    return (Join-Path $parent ("{0}_app" -f $name)).Replace('\\', '/')
}

function Get-CMakeCacheValue {
    param(
        [string]$CacheFile,
        [string]$Key
    )

    $match = Select-String -Path $CacheFile -Pattern "^$([regex]::Escape($Key)):[^=]*=(.*)$" | Select-Object -First 1
    if (-not $match) {
        return $null
    }

    return $match.Matches[0].Groups[1].Value
}

function Ensure-UnitBuildConfigured {
    if (Test-Path (Join-Path $BuildDir "CMakeCache.txt")) {
        return
    }

    $cmd = @("build")
    if ($PristineAlways) {
        $cmd += @("-p", "always")
    }
    $cmd += @("-b", $Board, "-s", $unitSourceDir, "-d", $BuildDir)
    if ($ExtraCmakeArgs.Count -gt 0) {
        $cmd += "--"
        $cmd += $ExtraCmakeArgs
    }
    if ($ExtraWestArgs.Count -gt 0) {
        $cmd += $ExtraWestArgs
    }

    & west @cmd
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Build-UnitEdk {
    Ensure-UnitBuildConfigured
    & west build -d $BuildDir -t llext-edk @ExtraWestArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Expand-UnitEdk {
    $edkArchive = Join-Path $BuildDir "zephyr/llext-edk.tar.xz"
    $zephyrBuildDir = Join-Path $BuildDir "zephyr"

    if (-not (Test-Path $edkArchive)) {
        throw "missing llext EDK archive at '$edkArchive'"
    }

    $edkInstallDir = Join-Path $zephyrBuildDir "llext-edk"
    if (Test-Path $edkInstallDir) {
        Remove-Item -Recurse -Force $edkInstallDir
    }

    & tar -xf $edkArchive -C $zephyrBuildDir
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Build-StandaloneUnitApp {
    Build-UnitEdk
    Expand-UnitEdk

    $appBuildDir = Get-UnitAppBuildDir
    Assert-BuildDir -Candidate $appBuildDir

    $cacheFile = Join-Path $BuildDir "CMakeCache.txt"
    $cCompiler = Get-CMakeCacheValue -CacheFile $cacheFile -Key "CMAKE_C_COMPILER"
    if ([string]::IsNullOrWhiteSpace($cCompiler)) {
        throw "failed to resolve C compiler from '$cacheFile'"
    }

        $edkInstallDir = (Resolve-Path (Join-Path $BuildDir "zephyr/llext-edk")).Path
    & cmake -S $unitAppSourceDir -B $appBuildDir `
        -DCMAKE_TOOLCHAIN_FILE="$unitAppSourceDir/toolchain.cmake" `
        -DCMAKE_C_COMPILER="$cCompiler" `
        -DLLEXT_EDK_INSTALL_DIR="$edkInstallDir"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    & cmake --build $appBuildDir
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    $stagedArtifactDir = Join-Path $BuildDir "llext"
    $stagedArtifact = Join-Path $stagedArtifactDir "$unitAppName.llext"
    if (-not (Test-Path $stagedArtifactDir)) {
        New-Item -ItemType Directory -Path $stagedArtifactDir | Out-Null
    }

    Copy-Item -Force (Join-Path $appBuildDir "$unitAppName.llext") $stagedArtifact
}

$repoRoot = Get-RepoRoot
$unitSourceDir = "applocation/NeuroLink/neuro_unit"
$unitAppSourceDir = Join-Path $repoRoot "applocation/NeuroLink/subprojects/neuro_unit_app"
$unitAppName = "neuro_unit_app"
$zenohPicoModuleFile = Join-Path $repoRoot "modules/lib/zenoh-pico/zephyr/CMakeLists.txt"
Set-Location $repoRoot
. $envScript -Activate -Strict

if ($CheckCStyle) {
    & pwsh -File "applocation/NeuroLink/scripts/check_neurolink_linux_c_style.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "linux c-style check failed. Run format_neurolink_c_style.ps1 -Fix, address remaining checkpatch findings, and retry."
    }
}

switch ($Preset) {
    "unit" {
        if (-not $BuildDir) {
            $BuildDir = "build/neurolink_unit"
        }
        Assert-BuildDir -Candidate $BuildDir
        Assert-ZenohPicoModule

        $cmd = @("build")
        if ($PristineAlways) {
            $cmd += @("-p", "always")
        }
        $cmd += @("-b", $Board, "-s", $unitSourceDir, "-d", $BuildDir)
        if ($ExtraCmakeArgs.Count -gt 0) {
            $cmd += "--"
            $cmd += $ExtraCmakeArgs
        }
        if ($ExtraWestArgs.Count -gt 0) {
            $cmd += $ExtraWestArgs
        }

        & west @cmd
        exit $LASTEXITCODE
    }
    "unit-ut" {
        if (-not $BuildDir) {
            $BuildDir = "build/neurolink_unit_ut"
        }
        Assert-BuildDir -Candidate $BuildDir

        $cmd = @("build")
        if ($PristineAlways) {
            $cmd += @("-p", "always")
        }
        $cmd += @("-b", $Board, "-s", "applocation/NeuroLink/neuro_unit/tests/unit", "-d", $BuildDir)
        if ($ExtraCmakeArgs.Count -gt 0) {
            $cmd += "--"
            $cmd += $ExtraCmakeArgs
        }
        if ($ExtraWestArgs.Count -gt 0) {
            $cmd += $ExtraWestArgs
        }

        & west @cmd
        exit $LASTEXITCODE
    }
    "unit-edk" {
        if (-not $BuildDir) {
            $BuildDir = "build/neurolink_unit"
        }
        Assert-BuildDir -Candidate $BuildDir
        Assert-ZenohPicoModule

        Build-UnitEdk
        Expand-UnitEdk
        exit 0
    }
    "unit-app" {
        if (-not $BuildDir) {
            $BuildDir = "build/neurolink_unit"
        }
        Assert-BuildDir -Candidate $BuildDir
        Assert-ZenohPicoModule

        Build-StandaloneUnitApp
        exit 0
    }
    "unit-ext" {
        if (-not $BuildDir) {
            $BuildDir = "build/neurolink_unit"
        }
        Assert-BuildDir -Candidate $BuildDir
        Assert-ZenohPicoModule

        Build-StandaloneUnitApp
        exit 0
    }
    "flash-unit" {
        if (-not $BuildDir) {
            $BuildDir = "build/neurolink_unit"
        }
        Assert-BuildDir -Candidate $BuildDir

        $cmd = @("flash", "-d", $BuildDir)
        if ($EspDevice) {
            $cmd += @("--esp-device", $EspDevice)
        }
        if ($ExtraWestArgs.Count -gt 0) {
            $cmd += $ExtraWestArgs
        }

        & west @cmd
        exit $LASTEXITCODE
    }
}
