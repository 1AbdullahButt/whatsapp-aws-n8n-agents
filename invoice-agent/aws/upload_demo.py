"""Upload the 12 synthetic invoices to the deployed inbox bucket and report what Lambda extracted.

    .venv\\Scripts\\python aws\\upload_demo.py

Waits until every file has an item in DynamoDB (up to about 3 minutes), then
prints status and flags per file and the field accuracy against expected.json,
counted the same way as scripts/accuracy_report.py does locally.
"""
import json
import time
from pathlib import Path

import boto3

PROJECT = Path(__file__).resolve().parents[1]
INVOICE_DIR = PROJECT / "synthetic" / "invoices"
EXPECTED = json.loads((PROJECT / "synthetic" / "expected.json").read_text(encoding="utf-8"))
STACK = "invoice-agent-b4"
REGION = "ap-southeast-2"
FIELDS = ["vendor", "invoice_number", "invoice_date", "due_date", "currency", "subtotal", "tax", "total", "line_items"]


def outputs():
    stack = boto3.client("cloudformation", region_name=REGION).describe_stacks(StackName=STACK)
    return {o["OutputKey"]: o["OutputValue"] for o in stack["Stacks"][0]["Outputs"]}


def same(found, expected):
    """Numbers come back from DynamoDB as Decimal; compare as rounded floats."""
    if isinstance(expected, (int, float)) and found is not None:
        return round(float(found), 2) == round(float(expected), 2)
    if isinstance(expected, list):
        return json.loads(json.dumps(found, default=float)) == expected
    return found == expected


def main():
    out = outputs()
    s3 = boto3.client("s3", region_name=REGION)
    table = boto3.resource("dynamodb", region_name=REGION).Table(out["TableName"])
    names = sorted(EXPECTED)
    for name in names:
        s3.upload_file(str(INVOICE_DIR / name), out["InboxBucketName"], name)
        time.sleep(0.5)   # keeps inv_01 ahead of its resent copy inv_09
    print(f"Uploaded {len(names)} PDFs. Waiting for Lambda...")
    items = {}
    for _ in range(36):
        for name in names:
            if name not in items:
                got = table.get_item(Key={"pk": f"INVOICE#{name}", "sk": "META"}).get("Item")
                if got:
                    items[name] = got
        if len(items) == len(names):
            break
        time.sleep(5)
    correct = total = 0
    for name in names:
        item = items.get(name)
        if item is None:
            print(f"{name:<28} NOT PROCESSED")
            continue
        expected = EXPECTED[name]["fields"]
        right = sum(same(item["fields"].get(f), expected.get(f)) for f in FIELDS)
        correct += right
        total += len(FIELDS)
        dup = f" (duplicate of {item['duplicate_of']})" if item.get("duplicate_of") else ""
        print(f"{name:<28} {item['status']:<13} {right}/{len(FIELDS)} fields{dup}  {','.join(item['flags'])}")
    print(f"Processed {len(items)}/{len(names)}. Fields correct: {correct}/{total}")


if __name__ == "__main__":
    main()
