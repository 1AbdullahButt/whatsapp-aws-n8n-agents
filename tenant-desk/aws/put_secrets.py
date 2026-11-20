"""Copy the three WhatsApp secrets from tenant-desk/.env into SSM Parameter Store.

    .venv\\Scripts\\python aws\\put_secrets.py

Standard-tier SecureString parameters (free), encrypted with the AWS-managed
aws/ssm key. Uses your `aws configure` credentials. Prints names only, never values.
Run it again after you generate a new WhatsApp token (it overwrites).
"""
import sys
from pathlib import Path

import boto3

TENANT_DESK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TENANT_DESK.parent))
from shared.config import load_env, require   # noqa: E402

PREFIX = "/tenant-desk"
SECRETS = {
    "whatsapp-token": "WHATSAPP_TOKEN",
    "app-secret": "WHATSAPP_APP_SECRET",
    "verify-token": "WHATSAPP_VERIFY_TOKEN",
}


def put_all(ssm, values):
    for name, env_name in SECRETS.items():
        ssm.put_parameter(Name=f"{PREFIX}/{name}", Value=values[env_name],
                          Type="SecureString", Tier="Standard", Overwrite=True)
        print(f"stored {PREFIX}/{name}")


def main():
    load_env(TENANT_DESK / ".env")
    values = {env_name: require(env_name).strip() for env_name in SECRETS.values()}
    put_all(boto3.client("ssm", region_name="us-east-1"), values)


if __name__ == "__main__":
    main()
