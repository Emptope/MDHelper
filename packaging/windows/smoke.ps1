param(
    [Parameter(Mandatory = $true)]
    [string]$DistributionDirectory,
    [Parameter(Mandatory = $true)]
    [string]$Request,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$checkScript = Join-Path $PSScriptRoot "../smoke_check.py"
$distribution = (Resolve-Path $DistributionDirectory).Path
$application = (& $Python $checkScript distribution `
    --root $distribution `
    --platform windows | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "Packaged distribution validation failed." }
$config = Join-Path $distribution "config.toml"
$requestPath = (Resolve-Path $Request).Path

$smokeRoot = Join-Path ([IO.Path]::GetTempPath()) ("mdhelper-smoke-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $smokeRoot | Out-Null
$previousConfig = $env:MDHELPER_CONFIG
$previousQtPlatform = $env:QT_QPA_PLATFORM
$previousPythonWarnings = $env:PYTHONWARNINGS
try {
    $env:PYTHONWARNINGS = "error"
    & $application --version | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Packaged version check failed." }
    & $application tui --smoke-test | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Packaged TUI startup check failed." }

    $env:MDHELPER_CONFIG = $null
    $configReport = & $application cli config check | Out-String
    if ($LASTEXITCODE -ne 0) { throw "Packaged CLI config validation failed." }
    $configReportPath = Join-Path $smokeRoot "config.json"
    [IO.File]::WriteAllText($configReportPath, $configReport)
    & $Python $checkScript config `
        --report $configReportPath `
        --expected-path $config
    if ($LASTEXITCODE -ne 0) { throw "Colocated configuration validation failed." }
    & $application cli templates list | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Packaged template catalog validation failed." }

    $env:QT_QPA_PLATFORM = "offscreen"
    & $application gui --smoke-test | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Packaged GUI startup check failed." }

    $analysisOutput = Join-Path $smokeRoot "analysis"
    Push-Location $projectRoot
    try {
        $analysisReport = & $application cli analyze request `
            --request $requestPath `
            --output $analysisOutput | Out-String
        $analysisStatus = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($analysisStatus -ne 0) { throw "Packaged analysis request failed." }
    $analysisReportPath = Join-Path $smokeRoot "analysis.json"
    [IO.File]::WriteAllText($analysisReportPath, $analysisReport)
    & $Python $checkScript analysis `
        --output $analysisOutput `
        --report $analysisReportPath
    if ($LASTEXITCODE -ne 0) { throw "Packaged analysis export validation failed." }
}
finally {
    $env:MDHELPER_CONFIG = $previousConfig
    $env:QT_QPA_PLATFORM = $previousQtPlatform
    $env:PYTHONWARNINGS = $previousPythonWarnings
    [IO.Directory]::Delete($smokeRoot, $true)
}
