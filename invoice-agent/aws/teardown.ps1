# Remove everything B4 created, then check nothing is left.
#   powershell -ExecutionPolicy Bypass -File aws\teardown.ps1
# Safe to run twice. Region us-east-1.

$ErrorActionPreference = "Continue"
$Region = "us-east-1"
$Stack = "invoice-agent-b4"

Write-Host "1. Empty the inbox bucket (CloudFormation cannot delete a bucket that has files)"
$bucket = aws cloudformation describe-stacks --stack-name $Stack --region $Region `
  --query "Stacks[0].Outputs[?OutputKey=='InboxBucketName'].OutputValue" --output text 2>$null
if ($bucket -and $bucket -ne "None") { aws s3 rm "s3://$bucket" --recursive --region $Region }

Write-Host "2. Delete the stack (Lambda, queues, table, bucket, log group, role)"
sam delete --stack-name $Stack --region $Region --no-prompts

Write-Host "3. Check what is left"
aws cloudformation list-stacks --region $Region `
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_FAILED ROLLBACK_COMPLETE `
  --query "StackSummaries[].StackName" --output text
aws lambda list-functions --region $Region --query "Functions[].FunctionName" --output text
aws sqs list-queues --region $Region --output text
aws dynamodb list-tables --region $Region --query "TableNames" --output text
aws s3 ls
Write-Host "Expected: nothing except 'aws-sam-cli-managed-default' and its bucket, which you remove"
Write-Host "last (after both A4 and B4 are torn down), see aws/README.md."
