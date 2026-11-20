"""Transcribe voice notes the AWS worker stored as "transcription pending".

    .venv\\Scripts\\python aws\\transcribe_pending.py

Runs on this PC with faster-whisper (free, local) and your `aws configure`
credentials: reads pending messages from the stack's DynamoDB table, gets the
audio from S3, writes the transcript back and updates the ticket.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3

TENANT_DESK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TENANT_DESK))
sys.path.insert(0, str(TENANT_DESK.parent))

from app.repo_dynamodb import DynamoRepository        # noqa: E402
from app.transcriber import FasterWhisperTranscriber  # noqa: E402
from cloud.pending import transcribe_pending          # noqa: E402

STACK = "tenant-desk-a4"
REGION = "us-east-1"


def main():
    stack = boto3.client("cloudformation", region_name=REGION).describe_stacks(StackName=STACK)
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Stacks"][0]["Outputs"]}
    repo = DynamoRepository(outputs["TableName"], region=REGION)
    done = transcribe_pending(repo, boto3.client("s3", region_name=REGION),
                              FasterWhisperTranscriber(), datetime.now(timezone.utc))
    for ticket_id, text in done:
        print(f"{ticket_id}: {text}")
    print(f"{len(done)} voice note(s) transcribed.")


if __name__ == "__main__":
    main()
