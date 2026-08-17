$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backendRoot = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $repoRoot ".venv-cuda\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "CUDA backend environment is missing: $pythonPath"
}

$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
Set-Location -LiteralPath $backendRoot
& $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
