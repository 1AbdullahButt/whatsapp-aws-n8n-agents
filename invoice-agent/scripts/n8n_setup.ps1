# Import the two workflows into the invoice-agent n8n and publish (activate)
# both. Safe to run again: import overwrites by workflow id.
#
# Run from anywhere, after `docker compose up -d --build`:
#   powershell -ExecutionPolicy Bypass -File scripts\n8n_setup.ps1
#
# n8n 2.x: `update:workflow --active=true` is deprecated; `publish:workflow`
# replaces it. "Invoice errors" must be published too: n8n 2.48.7 logs
# 'Workflow "InvoiceErrors001" is not active and cannot be executed'
# otherwise (found on the first e2e run).

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)    # invoice-agent folder

function Invoke-N8n {
    param([string[]]$CliArgs)
    # -T: no TTY, -u node: run as the n8n user inside the container
    docker compose exec -T -u node n8n n8n @CliArgs
    if ($LASTEXITCODE -ne 0) { throw "n8n $($CliArgs -join ' ') failed (exit $LASTEXITCODE)" }
}

function Wait-N8n {
    # /healthz answers before the database migrations are done. Running a
    # CLI command during the migrations breaks them, so wait for
    # /healthz/readiness, which only says ok once the database is ready.
    Write-Host "Waiting for n8n on http://localhost:5690 ..."
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://localhost:5690/healthz/readiness
            if ($r.StatusCode -eq 200) { Write-Host "n8n is ready."; return }
        } catch { }
        Start-Sleep -Seconds 2
    }
    throw "n8n was not ready on http://localhost:5690/healthz/readiness"
}

Wait-N8n

Write-Host "Importing workflows from n8n/workflows ..."
Invoke-N8n @("import:workflow", "--separate", "--input=/workflows")

foreach ($id in @("InvoiceErrors001", "InvoiceIntake001")) {
    Write-Host "Publishing workflow $id ..."
    Invoke-N8n @("publish:workflow", "--id=$id")
}

# Restart so the webhook is registered for sure (the publication service
# would also pick it up within about 15 seconds).
Write-Host "Restarting n8n ..."
docker compose restart n8n
if ($LASTEXITCODE -ne 0) { throw "docker compose restart n8n failed" }
Wait-N8n

Invoke-N8n @("list:workflow")
Write-Host "Done. Webhook: POST http://localhost:5690/webhook/invoice  {""filename"": ""inv_01_classic_usd.pdf""}"
