param(
    [Parameter(Mandatory = $true)]
    [string]$Archive,
    [string]$Request = ""
)

$ErrorActionPreference = "Stop"
$archivePath = (Resolve-Path $Archive).Path
$smokeRoot = Join-Path ([IO.Path]::GetTempPath()) ("mdhelper-archive-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $smokeRoot | Out-Null
try {
    Expand-Archive -Path $archivePath -DestinationPath $smokeRoot
    $executables = @(Get-ChildItem $smokeRoot -Filter "mdhelper.exe" -File -Recurse)
    if ($executables.Count -ne 1) {
        throw "Expected one packaged application, found $($executables.Count)."
    }
    & (Join-Path $PSScriptRoot "smoke.ps1") `
        -DistributionDirectory $executables[0].Directory.FullName `
        -Request $Request
    if ($LASTEXITCODE -ne 0) { throw "Extracted application smoke test failed." }
}
finally {
    if (Test-Path $smokeRoot) {
        [IO.Directory]::Delete($smokeRoot, $true)
    }
}
