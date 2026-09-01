param(
    [Parameter(Mandatory = $true)]
    [string]$DistributionDirectory,
    [string]$Request = ""
)

$ErrorActionPreference = "Stop"
$distribution = (Resolve-Path $DistributionDirectory).Path
$application = Join-Path $distribution "mdhelper.exe"
if (-not (Test-Path -PathType Leaf $application)) {
    throw "Missing packaged application: $application"
}
$executables = @(Get-ChildItem $distribution -Filter "*.exe" -File)
$unexpectedExecutables = @(
    $executables | Where-Object { $_.Name -ne "mdhelper.exe" }
)
if ($unexpectedExecutables.Count -ne 0) {
    $names = ($unexpectedExecutables.Name | Sort-Object) -join ", "
    throw "Unexpected packaged executables: $names"
}
$config = Join-Path $distribution "config.toml"
if (-not (Test-Path -PathType Leaf $config)) {
    throw "Packaged distribution is missing its colocated configuration: $config"
}

$smokeRoot = Join-Path ([IO.Path]::GetTempPath()) ("mdhelper-smoke-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $smokeRoot | Out-Null
$previousConfig = $env:MDHELPER_CONFIG
$previousQtPlatform = $env:QT_QPA_PLATFORM
$previousPythonWarnings = $env:PYTHONWARNINGS
$previousGuiProcess = $env:MDHELPER_GUI_PROCESS
try {
    $env:PYTHONWARNINGS = "error"
    & $application --version | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Packaged version check failed." }
    & $application tui --smoke-test | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Packaged TUI startup check failed." }

    $env:MDHELPER_CONFIG = $null
    $reportedConfig = (& $application cli config path | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Colocated config path check failed." }
    if (-not [string]::Equals(
        [IO.Path]::GetFullPath($reportedConfig),
        [IO.Path]::GetFullPath($config),
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Packaged CLI selected '$reportedConfig' instead of '$config'."
    }
    & $application cli config check | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Packaged CLI config validation failed." }
    & $application cli templates list | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Packaged template catalog validation failed." }

    $env:QT_QPA_PLATFORM = "offscreen"
    $env:MDHELPER_GUI_PROCESS = "1"
    & $application gui --smoke-test | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Packaged GUI startup check failed." }

    if ($Request) {
        $requestPath = (Resolve-Path $Request).Path
        $analysisOutput = Join-Path $smokeRoot "analysis"
        & $application cli analyze request --request $requestPath --output $analysisOutput | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Packaged analysis request failed." }
        foreach ($name in @("result.json", "rdf.csv", "rdf.png", "rdf.svg", "rdf.pdf")) {
            $path = Join-Path $analysisOutput $name
            if (-not (Test-Path -PathType Leaf $path)) {
                throw "Packaged analysis did not export the required file: $path"
            }
        }
    }
}
finally {
    $env:MDHELPER_CONFIG = $previousConfig
    $env:QT_QPA_PLATFORM = $previousQtPlatform
    $env:PYTHONWARNINGS = $previousPythonWarnings
    $env:MDHELPER_GUI_PROCESS = $previousGuiProcess
    [IO.Directory]::Delete($smokeRoot, $true)
}
