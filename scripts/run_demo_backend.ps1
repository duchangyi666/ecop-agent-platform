param(
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"

# Load local demo configuration. Explicit process env wins (useful for
# AUTH_MODE=oidc smoke tests); .env fills anything not already set.
if (Test-Path $envFile) {
    Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $separator = $line.IndexOf("=")
        if ($separator -lt 1) { return }
        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        $existing = [Environment]::GetEnvironmentVariable($name, "Process")
        if ($name -and [string]::IsNullOrEmpty($existing)) {
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
