param(
    [string]$Python = "python",
    [string]$OutputDirectory = "dist/windows",
    [string]$SmokeRequest = "",
    [int]$MaxArtifactSizeMB = 256
)

$ErrorActionPreference = "Stop"
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "The Windows release must be built on Windows x64."
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$distRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "dist"))
$releaseOutput = [IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory))
$distPrefix = $distRoot + [IO.Path]::DirectorySeparatorChar
if (-not $releaseOutput.StartsWith($distPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "The release output must be a platform directory under dist: $releaseOutput"
}
$stage = Join-Path $projectRoot "build/package-windows"
$applicationOutput = Join-Path $stage "application"
$work = Join-Path $projectRoot "build/pyinstaller-windows"
$version = (& $Python -c "import mdhelper; print(mdhelper.__version__)").Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not determine the MDHelper version." }

if (Test-Path $stage) {
    [IO.Directory]::Delete($stage, $true)
}
if (Test-Path $releaseOutput) {
    [IO.Directory]::Delete($releaseOutput, $true)
}

& $Python -m PyInstaller `
    --clean `
    --noconfirm `
    --distpath $applicationOutput `
    --workpath $work `
    (Join-Path $PSScriptRoot "mdhelper.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }

$application = Join-Path $applicationOutput "mdhelper.exe"
& $Python (Join-Path $projectRoot "packaging/frozen_audit.py") `
    --application $application `
    --platform windows `
    --max-size-mb $MaxArtifactSizeMB
if ($LASTEXITCODE -ne 0) { throw "Packaged executable audit failed." }

& $Python (Join-Path $projectRoot "packaging/generate_notices.py") `
    --output (Join-Path $applicationOutput "THIRD_PARTY_NOTICES.json")
if ($LASTEXITCODE -ne 0) { throw "Dependency notice generation failed." }

Copy-Item (Join-Path $projectRoot "README.md") $applicationOutput -Force
Copy-Item (Join-Path $projectRoot "README.zh-CN.md") $applicationOutput -Force
Copy-Item (Join-Path $projectRoot "LICENSE") $applicationOutput -Force
Copy-Item (Join-Path $projectRoot "config.example.toml") $applicationOutput -Force
Copy-Item (Join-Path $projectRoot "config.example.toml") `
    (Join-Path $applicationOutput "config.toml") -Force
Copy-Item (Join-Path $projectRoot "docs") $applicationOutput -Recurse -Force
Copy-Item (Join-Path $projectRoot "schemas") $applicationOutput -Recurse -Force

& (Join-Path $PSScriptRoot "smoke.ps1") `
    -DistributionDirectory $applicationOutput `
    -Request $SmokeRequest
if ($LASTEXITCODE -ne 0) { throw "Packaged executable smoke test failed." }

$archiveName = "MDHelper-$version-Windows-x64"
$archiveRoot = Join-Path $stage $archiveName
$archivePath = Join-Path $releaseOutput "$archiveName.zip"
New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null
Copy-Item (Join-Path $applicationOutput "*") $archiveRoot -Recurse -Force
New-Item -ItemType Directory -Path $releaseOutput -Force | Out-Null
Compress-Archive `
    -Path $archiveRoot `
    -DestinationPath $archivePath `
    -CompressionLevel Optimal `
    -Force

& $Python (Join-Path $projectRoot "packaging/frozen_audit.py") `
    --artifact $archivePath `
    --platform windows `
    --max-size-mb $MaxArtifactSizeMB
if ($LASTEXITCODE -ne 0) { throw "Release archive size audit failed." }

& (Join-Path $PSScriptRoot "archive_smoke.ps1") `
    -Archive $archivePath `
    -Request $SmokeRequest
if ($LASTEXITCODE -ne 0) { throw "Release archive smoke test failed." }
Write-Host "Windows archive: $archivePath"
