"""Lambda settings: plain values from environment variables, secrets from SSM.

Secrets live in SSM Parameter Store (standard tier, SecureString, free).
The Lambda environment only holds the parameter *names*, so the secret
values never appear in the CloudFormation template or the Lambda console.
"""
import os
import time

import boto3

# Secrets are re-read from SSM after this many seconds, so a new WhatsApp token
# (put_secrets.py) reaches a warm Lambda within 5 minutes without a redeploy.
CACHE_SECONDS = 300
_cache = {}   # name -> (value, time it was read)

SECRET_NAMES = {
    "whatsapp_token": "WHATSAPP_TOKEN_PARAM",
    "app_secret": "APP_SECRET_PARAM",
    "verify_token": "VERIFY_TOKEN_PARAM",
}


def region():
    return os.environ.get("AWS_REGION", "ap-southeast-2")


def secret(name, clock=time.monotonic):
    """Read one SecureString from SSM, reusing it for CACHE_SECONDS."""
    cached = _cache.get(name)
    if cached and clock() - cached[1] < CACHE_SECONDS:
        return cached[0]
    param_name = os.environ[SECRET_NAMES[name]]
    ssm = boto3.client("ssm", region_name=region())
    value = ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]
    _cache[name] = (value, clock())
    return value


def clear_cache():
    _cache.clear()


def env(name):
    return os.environ[name]
