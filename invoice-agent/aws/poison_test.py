"""Show retries and the dead-letter queue on the deployed B4 stack.

    .venv\\Scripts\\python aws\\poison_test.py

Uploads a file named .pdf that is not a PDF. The Lambda fails to read it,
SQS retries, and after 3 receives the event moves to the dead-letter queue
(the queue's visibility timeout is 6 minutes, so this takes up to ~15 minutes).
"""
import json
import time

import boto3

STACK = "invoice-agent-b4"
REGION = "ap-southeast-2"
KEY = "poison_not_a_pdf.pdf"


def main():
    stack = boto3.client("cloudformation", region_name=REGION).describe_stacks(StackName=STACK)
    out = {o["OutputKey"]: o["OutputValue"] for o in stack["Stacks"][0]["Outputs"]}
    boto3.client("s3", region_name=REGION).put_object(Bucket=out["InboxBucketName"], Key=KEY,
                                                       Body=b"this is not a pdf")
    sqs = boto3.client("sqs", region_name=REGION)
    print("Uploaded a broken PDF. Waiting for its event in the dead-letter queue (up to ~20 min)...")
    for _ in range(120):
        time.sleep(10)
        got = sqs.receive_message(QueueUrl=out["DeadLetterQueueUrl"], MaxNumberOfMessages=1,
                                  AttributeNames=["ApproximateReceiveCount"], VisibilityTimeout=5)
        for message in got.get("Messages", []):
            if KEY in message["Body"]:
                key = json.loads(message["Body"])["Records"][0]["s3"]["object"]["key"]
                print(f"Found in the dead-letter queue: S3 event for {key}")
                sqs.delete_message(QueueUrl=out["DeadLetterQueueUrl"], ReceiptHandle=message["ReceiptHandle"])
                return 0
    print("Not in the dead-letter queue yet. Check the Lambda logs in CloudWatch.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
