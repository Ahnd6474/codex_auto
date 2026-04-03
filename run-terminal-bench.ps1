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

if (-not (Get-Command harbor -ErrorAction SilentlyContinue)) {
    throw "harbor is not installed or not on PATH."
}

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
if (-not $UseLocalSource.IsPresent -and $Mode -eq "smoke") {
    $UseLocalSource = $true
}

if (-not $env:OPENAI_API_KEY) {
    throw "OPENAI_API_KEY is not set."
}

$harborArgs = @(
    "run",
    "-d", $Dataset,
    "--agent-import-path", $AgentImportPath,
    "-k", "$Attempts",
    "-n", "$Concurrent",
    "--yes"
)

if ($Mode -eq "smoke") {
    foreach ($task in $Tasks) {
        $harborArgs += @("-i", $task)
    }
    $harborArgs += @("-l", "$($Tasks.Count)")
}

if ($KeepEnvironment.IsPresent) {
    $harborArgs += "--no-delete"
}

if ($UseLocalSource.IsPresent) {
    $mountsJson = @(
        @{
            type = "bind"
            source = $repoRoot
            target = "/opt/jakal-flow-src"
            read_only = $true
        }
    ) | ConvertTo-Json -Compress -AsArray
    $harborArgs += @("--mounts-json", $mountsJson)
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

Write-Host "Running Harbor with args:" -ForegroundColor Cyan
Write-Host ("harbor " + ($harborArgs -join " ")) -ForegroundColor Yellow

& harbor @harborArgs
exit $LASTEXITCODE
