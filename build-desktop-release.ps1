param(
    [ValidateSet("full", "python", "lean", "all")]
    [string]$Profile = "python"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcRoot = Join-Path $repoRoot "src"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }
$actionByProfile = @{
    full = "build-full"
    python = "build-python"
    lean = "build-lean"
    all = "build-all"
}

if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $srcRoot
} else {
    $env:PYTHONPATH = "$srcRoot;$($env:PYTHONPATH)"
}

Set-Location $repoRoot

& $python "-m" "jakal_flow.desktop" $actionByProfile[$Profile]
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$releaseRoot = Join-Path $repoRoot "release"
if (-not (Test-Path $releaseRoot)) {
    throw "Release directory was not created: $releaseRoot"
}

$artifacts = Get-ChildItem -Path $releaseRoot -File |
    Where-Object { $_.Extension -in ".exe", ".msi" } |
    Sort-Object LastWriteTime -Descending

if (-not $artifacts) {
    throw "No release artifacts were found in $releaseRoot"
}

Write-Host "Desktop release artifacts:"
foreach ($artifact in $artifacts) {
    Write-Host (" - {0}" -f $artifact.Name)
}
