param(
    [string]$TenantSlug = "clouddesk-demo",
    [string]$BaseUrl = "http://127.0.0.1:3000",
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "frontend"

if ($env:AUTH_MODE -ne "dev" -or -not $env:DATABASE_URL) {
    throw "Set AUTH_MODE=dev and DATABASE_URL for the isolated demo database first."
}

$uri = [Uri]$BaseUrl
if ($uri.Host -notin @("localhost", "127.0.0.1", "::1")) {
    throw "The demo smoke runner only accepts a local frontend URL."
}

# Do not persist the generated identifiers or change the caller's environment.
$previousBaseUrl = $env:SMOKE_BASE_URL
$previousTenantSlug = $env:SMOKE_TENANT_SLUG
$previousPaymentId = $env:SMOKE_PAYMENT_ID
Push-Location $root
try {
    $seedOutput = & $PythonExecutable scripts/seed_demo_scenario.py --tenant-slug $TenantSlug
    if ($LASTEXITCODE -ne 0) {
        throw "Demo scenario seed failed (exit code $LASTEXITCODE)."
    }
    $scenario = ($seedOutput -join "`n") | ConvertFrom-Json
    if (-not $scenario.payment_id) {
        throw "Demo scenario seed did not return a payment ID."
    }

    $env:SMOKE_BASE_URL = $BaseUrl.TrimEnd("/")
    $env:SMOKE_TENANT_SLUG = $TenantSlug
    $env:SMOKE_PAYMENT_ID = $scenario.payment_id
    Set-Location $frontend
    & npm run test:demo
    if ($LASTEXITCODE -ne 0) {
        throw "Demo browser checks failed (exit code $LASTEXITCODE)."
    }
} finally {
    $env:SMOKE_BASE_URL = $previousBaseUrl
    $env:SMOKE_TENANT_SLUG = $previousTenantSlug
    $env:SMOKE_PAYMENT_ID = $previousPaymentId
    Pop-Location
}
