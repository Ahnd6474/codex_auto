param(
    [ValidateSet("smoke", "full")]
    [string]$Mode = "smoke",
    [string[]]$Tasks = @("fix-git", "regex-log", "polyglot-c-py"),
    [int]$Attempts = 1,
    [int]$Concurrent = 1,
    [switch]$UseLocalSource,
    [switch]$KeepEnvironment,
    [string]$Dataset = "terminal-bench@2.0",
    [string]$AgentImportPath = "jakal_flow.terminal_bench_agent:JakalFlowInstalledAgent"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $dockerPath = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    if (Test-Path $dockerPath) {
        $env:PATH = "$([System.IO.Path]::GetDirectoryName($dockerPath));$env:PATH"
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker is not available on PATH."
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcPath = Join-Path $repoRoot "src"
$codexHome = Join-Path $HOME ".codex"
if (-not $UseLocalSource.IsPresent -and $Mode -eq "smoke") {
    $UseLocalSource = $true
}

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw "codex CLI is not installed or not on PATH."
}

if (-not (Test-Path (Join-Path $codexHome "auth.json"))) {
    throw "Codex CLI auth was not found at $codexHome\auth.json. Run 'codex login' first."
}

$runner = @()
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $runner = @("uv", "tool", "run", "--from", "harbor", "--with", "terminal-bench", "harbor")
}
elseif (Get-Command harbor -ErrorAction SilentlyContinue) {
    $runner = @("harbor")
}
else {
    throw "Either uv or harbor must be installed and available on PATH."
}

$harborArgs = @(
    "run",
    "--yes"
)

$mounts = @(
    @{
        type = "bind"
        source = $codexHome
        target = "/opt/codex-home"
        read_only = $true
    }
)

if ($UseLocalSource.IsPresent) {
    $mounts += @{
        type = "bind"
        source = $repoRoot
        target = "/opt/jakal-flow-src"
        read_only = $true
    }
    $env:JAKAL_FLOW_GIT_URL = "/opt/jakal-flow-src"
    if (-not $env:JAKAL_FLOW_GIT_REF) {
        $env:JAKAL_FLOW_GIT_REF = "main"
    }
}

if (-not $env:JAKAL_FLOW_MODEL_PROVIDER) {
    $env:JAKAL_FLOW_MODEL_PROVIDER = "openai"
}
if (-not $env:JAKAL_FLOW_MODEL) {
    $env:JAKAL_FLOW_MODEL = "gpt-5.4"
}
if (-not $env:JAKAL_FLOW_EFFORT) {
    $env:JAKAL_FLOW_EFFORT = "high"
}
if (-not $env:JAKAL_FLOW_MAX_BLOCKS) {
    $env:JAKAL_FLOW_MAX_BLOCKS = "12"
}
if (-not $env:CODEX_HOME) {
    $env:CODEX_HOME = "/opt/codex-home"
}
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
}
else {
    $env:PYTHONPATH = $srcPath
}

$datasetConfig = @{
    name = "terminal-bench"
    version = "2.0"
}

if ($Mode -eq "smoke") {
    $datasetConfig.task_names = @($Tasks)
    $datasetConfig.n_tasks = $Tasks.Count
}

$jobConfig = @{
    n_attempts = $Attempts
    n_concurrent_trials = $Concurrent
    quiet = $true
    agents = @(
        @{
            import_path = $AgentImportPath
            model_name = "$($env:JAKAL_FLOW_MODEL_PROVIDER)/$($env:JAKAL_FLOW_MODEL)"
        }
    )
    environment = @{
        type = "docker"
        delete = (-not $KeepEnvironment.IsPresent)
        mounts_json = @($mounts)
    }
    datasets = @($datasetConfig)
}

$tempConfigPath = Join-Path ([System.IO.Path]::GetTempPath()) ("jakal-flow-terminal-bench-" + [System.Guid]::NewGuid().ToString("N") + ".json")
$jsonText = ConvertTo-Json -InputObject $jobConfig -Depth 8
[System.IO.File]::WriteAllText($tempConfigPath, $jsonText, [System.Text.UTF8Encoding]::new($false))
$harborArgs += @("--config", $tempConfigPath)

Write-Host "Running Harbor with args:" -ForegroundColor Cyan
Write-Host (($runner -join " ") + " " + ($harborArgs -join " ")) -ForegroundColor Yellow

try {
    $runnerExecutable = $runner[0]
    $runnerArgs = @()
    if ($runner.Length -gt 1) {
        $runnerArgs = $runner[1..($runner.Length - 1)]
    }
    & $runnerExecutable @runnerArgs @harborArgs
    exit $LASTEXITCODE
}
finally {
    Remove-Item -LiteralPath $tempConfigPath -Force -ErrorAction SilentlyContinue
}
