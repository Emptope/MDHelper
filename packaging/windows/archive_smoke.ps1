param(
    [Parameter(Mandatory = $true)]
    [string]$Archive,
    [Parameter(Mandatory = $true)]
    [string]$Request,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$archivePath = (Resolve-Path $Archive).Path
$checkScript = Join-Path $PSScriptRoot "../smoke_check.py"
$expectedName = [IO.Path]::GetFileNameWithoutExtension($archivePath)
$smokeRoot = Join-Path ([IO.Path]::GetTempPath()) ("mdhelper-archive-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $smokeRoot | Out-Null
try {
    Expand-Archive -Path $archivePath -DestinationPath $smokeRoot
    $distribution = (& $Python $checkScript archive-root `
        --root $smokeRoot `
        --expected-name $expectedName | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Release archive layout validation failed." }
    & (Join-Path $PSScriptRoot "smoke.ps1") `
        -DistributionDirectory $distribution `
        -Request $Request `
        -Python $Python
    if ($LASTEXITCODE -ne 0) { throw "Extracted application smoke test failed." }
}
finally {
    if (Test-Path $smokeRoot) {
        [IO.Directory]::Delete($smokeRoot, $true)
    }
}
