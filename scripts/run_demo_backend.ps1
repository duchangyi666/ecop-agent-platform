param(
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"

# Load local demo configuration. Values in .env win over inherited process
# environment so filling DEEPSEEK_API_KEY there is enough for a restart.
if (Test-Path $envFile) {
    Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $separator = $line.IndexOf("=")
        if ($separator -lt 1) { return }
        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if ($name) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:54330/enterprise_customer_operations"
}
if (-not $env:MILVUS_URI) {
    $env:MILVUS_URI = "http://localhost:19541"
}
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONUTF8 = "1"

$python = Join-Path $root ".venv\Scripts\python.exe"
Write-Host "starting backend on http://${ListenHost}:${Port} (model key: $([bool]$env:DEEPSEEK_API_KEY))"
& $python -m uvicorn backend.main:app --host $ListenHost --port $Port
