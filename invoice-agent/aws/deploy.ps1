# Build and deploy the B4 stack. SAM shows the change set and waits for "y" before creating anything.
#   powershell -ExecutionPolicy Bypass -File aws\deploy.ps1
# Run from invoice-agent\. Needs: aws configure done and the budgets created.

$ErrorActionPreference = "Stop"
$Stack = "invoice-agent-b4"
$Region = "us-east-1"

# The venv's Python 3.12 must come first on PATH (Lambda runtime python3.12; plain `python` here is 3.10).
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"

python aws\build.py
sam build --template aws\template.yaml --build-dir .aws-sam\build
sam deploy --template .aws-sam\build\template.yaml --stack-name $Stack --region $Region `
  --resolve-s3 --capabilities CAPABILITY_IAM --confirm-changeset

aws cloudformation describe-stacks --stack-name $Stack --region $Region `
  --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output table
