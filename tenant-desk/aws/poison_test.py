"""Show the retry + dead-letter path on the deployed stack.

    .venv\\Scripts\\python aws\\poison_test.py

Puts one message that is not valid JSON on the main queue. The worker fails
on it (before any dedupe), SQS retries it, and after 3 receives it moves to
the dead-letter queue. The script waits up to about 5 minutes for that and
prints what it finds. It sends nothing to WhatsApp.
"""
import time

import boto3

STACK = "tenant-desk-a4"
POISON_BODY = "this is not json (poison test)"


def stack_outputs(cloudformation):
    stack = cloudformation.describe_stacks(StackName=STACK)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}


def main():
    region = "ap-southeast-2"
    outputs = stack_outputs(boto3.client("cloudformation", region_name=region))
    sqs = boto3.client("sqs", region_name=region)
    sqs.send_message(QueueUrl=outputs["QueueUrl"], MessageBody=POISON_BODY)
    print("Poison message sent. Waiting for it in the dead-letter queue...")
    for _ in range(30):
        time.sleep(10)
        got = sqs.receive_message(QueueUrl=outputs["DeadLetterQueueUrl"], MaxNumberOfMessages=1,
                                  AttributeNames=["ApproximateReceiveCount"], VisibilityTimeout=5)
        for message in got.get("Messages", []):
            if message["Body"] == POISON_BODY:
                print("Found in the dead-letter queue:", message["Body"])
                sqs.delete_message(QueueUrl=outputs["DeadLetterQueueUrl"],
                                   ReceiptHandle=message["ReceiptHandle"])
                print("Deleted it from the dead-letter queue.")
                return 0
    print("Not in the dead-letter queue after about 5 minutes. Check the worker logs.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
