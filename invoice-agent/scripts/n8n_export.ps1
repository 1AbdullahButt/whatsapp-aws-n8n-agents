# Export both workflows from the running invoice-agent n8n and save them,
# sanitised, to n8n/workflows/ (no credentials, no instance id, no pinData).
#
#   powershell -ExecutionPolicy Bypass -File scripts\n8n_export.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)    # invoice-agent folder

$workflows = @{
    "InvoiceIntake001" = "invoice_intake.json"
    "InvoiceErrors001" = "invoice_errors.json"
}
$tempDir = Join-Path $env:TEMP "invoice-agent-n8n-export"
New-Item -ItemType Directory -Force $tempDir | Out-Null

foreach ($id in $workflows.Keys) {
    $file = $workflows[$id]
    docker compose exec -T -u node n8n n8n export:workflow --id=$id --output=/tmp/$file
    if ($LASTEXITCODE -ne 0) { throw "export of $id failed" }
    docker compose cp "n8n:/tmp/$file" (Join-Path $tempDir $file)
    if ($LASTEXITCODE -ne 0) { throw "copy of $file failed" }
    & .venv\Scripts\python scripts\sanitize_workflow.py (Join-Path $tempDir $file) "n8n\workflows\$file"
    if ($LASTEXITCODE -ne 0) { throw "sanitising $file failed" }
}
Remove-Item -Recurse -Force $tempDir
