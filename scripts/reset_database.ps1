$ErrorActionPreference = "Stop"
$databasePath = Join-Path $PSScriptRoot "..\backend\data\personal_learning.sqlite3"
$resolvedBackend = Resolve-Path (Join-Path $PSScriptRoot "..\backend")

if (Test-Path -LiteralPath $databasePath) {
    $resolvedDatabase = (Resolve-Path -LiteralPath $databasePath).Path
    if (-not $resolvedDatabase.StartsWith($resolvedBackend.Path)) {
        throw "拒绝删除后端目录之外的数据库：$resolvedDatabase"
    }
    Remove-Item -LiteralPath $resolvedDatabase
}

Push-Location $resolvedBackend.Path
try {
    python -m alembic upgrade head
}
finally {
    Pop-Location
}

Write-Host "本地开发数据库已重置。"

