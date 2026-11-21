# Build and deploy the A4 stack. SAM shows the change set and waits for "y" before creating anything.
#   powershell -ExecutionPolicy Bypass -File aws\deploy.ps1
# Run from tenant-desk\. Needs: aws configure done, budgets created, aws\put_secrets.py run once.

$ErrorActionPreference = "Stop"
$Stack = "tenant-desk-a4"
$Region = "ap-southeast-2"

# The venv's Python 3.12 must come first on PATH, because the Lambda runtime is python3.12
# and plain `python` on this PC is 3.10.
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"

# The phone number ID is not a secret; read it from .env without printing it.
$line = Get-Content .env | Where-Object { $_ -match '^\s*WHATSAPP_PHONE_NUMBER_ID\s*=' }
$PhoneId = ($line -split '=', 2)[1].Trim().Trim('"')
if ($PhoneId -notmatch '^\d+$') { throw "WHATSAPP_PHONE_NUMBER_ID in .env must be digits only" }

python aws\build.py
sam build --template aws\template.yaml --build-dir .aws-sam\build
sam deploy --template .aws-sam\build\template.yaml --stack-name $Stack --region $Region `
  --resolve-s3 --capabilities CAPABILITY_IAM --confirm-changeset `
  --parameter-overrides "PhoneNumberId=$PhoneId"

aws cloudformation describe-stacks --stack-name $Stack --region $Region `
  --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output table
