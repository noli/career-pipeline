# Career Pipeline Quick Runner for Windows (PowerShell)
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PipelineArgs
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$env:PYTHONPATH = "$ScriptDir\src;" + $env:PYTHONPATH

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run --project $ScriptDir python -m career_pipeline.cli @PipelineArgs
} else {
    python -m career_pipeline.cli @PipelineArgs
}
