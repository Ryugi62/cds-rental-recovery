"""The only place boto3 clients are created. Creation only; nothing here calls AWS."""
from __future__ import annotations

_SERVICES = {"ses": "ses", "eum": "pinpoint-sms-voice-v2", "bedrock": "bedrock-runtime"}


def make_client(service: str, region: str, boto3_module=None):
    if boto3_module is None:
        import boto3 as boto3_module  # lazy: importing this module never touches AWS
    return boto3_module.client(_SERVICES[service], region_name=region)
