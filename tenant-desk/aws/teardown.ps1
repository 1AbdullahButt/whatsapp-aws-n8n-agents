# Remove everything A4 created, then check nothing is left.
#   powershell -ExecutionPolicy Bypass -File aws\teardown.ps1
# Safe to run twice. Uses your `aws configure` credentials, region us-east-1.

$ErrorActionPreference = "Continue"
$Region = "us-east-1"
$Stack = "tenant-desk-a4"

Write-Host "1. Empty the voice-note bucket (CloudFormation cannot delete a bucket that has files)"
$bucket = aws cloudformation describe-stacks --stack-name $Stack --region $Region `
  --query "Stacks[0].Outputs[?OutputKey=='MediaBucketName'].OutputValue" --output text 2>$null
if ($bucket -and $bucket -ne "None") { aws s3 rm "s3://$bucket" --recursive --region $Region }

Write-Host "2. Delete the stack (Lambdas, function URL, queues, table, bucket, log groups, roles)"
sam delete --stack-name $Stack --region $Region --no-prompts

Write-Host "3. Delete the three SSM parameters"
aws ssm delete-parameters --region $Region `
  --names /tenant-desk/whatsapp-token /tenant-desk/app-secret /tenant-desk/verify-token

Write-Host "4. Check: stacks still alive, Lambda functions, queues, tables, parameters"
aws cloudformation list-stacks --region $Region `
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_FAILED ROLLBACK_COMPLETE `
  --query "StackSummaries[].StackName" --output text
aws lambda list-functions --region $Region --query "Functions[].FunctionName" --output text
aws sqs list-queues --region $Region --output text
aws dynamodb list-tables --region $Region --query "TableNames" --output text
aws ssm describe-parameters --region $Region --query "Parameters[].Name" --output text
Write-Host "Expected: nothing above except possibly 'aws-sam-cli-managed-default' (SAM's own"
Write-Host "artifact bucket stack; see aws/README.md for how to remove it after B4)."
