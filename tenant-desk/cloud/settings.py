"""Lambda settings: plain values from environment variables, secrets from SSM.

Secrets live in SSM Parameter Store (standard tier, SecureString, free).
The Lambda environment only holds the parameter *names*, so the secret
values never appear in the CloudFormation template or the Lambda console.
"""
import os
from functools import lru_cache

import boto3

SECRET_NAMES = {
    "whatsapp_token": "WHATSAPP_TOKEN_PARAM",
    "app_secret": "APP_SECRET_PARAM",
    "verify_token": "VERIFY_TOKEN_PARAM",
}


def region():
    return os.environ.get("AWS_REGION", "us-east-1")


@lru_cache(maxsize=None)
def secret(name):
    """Read one SecureString once per Lambda container (cold start), then reuse it."""
    param_name = os.environ[SECRET_NAMES[name]]
    ssm = boto3.client("ssm", region_name=region())
    return ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]


def env(name):
    return os.environ[name]
