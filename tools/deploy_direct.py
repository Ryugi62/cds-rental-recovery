"""Deploy what template.yaml describes without CloudFormation, as far as the deploying IAM user allows
(composition root, not unit-tested: it calls AWS). Usage:
  AWS_PROFILE=<p> CDS_LAMBDA_ROLE=<existing role name with AWSLambdaBasicExecutionRole> python3 tools/deploy_direct.py deploy
  AWS_PROFILE=<p> python3 tools/deploy_direct.py invoke     # one invocation per canned event shape, results logged
Creates or updates: the SMS configuration set `cds-rr-sms` and the Lambda function `cds-rr-events`
(handler infrastructure.lambda_handlers.events_handler). It creates no IAM role and changes no policy.
SNS topics, subscriptions and SES receiving are skipped and logged when the user is not allowed to create them.
Log: docs/live/deploy-log.jsonl (account ids masked)."""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "docs/live/deploy-log.jsonl"
REGION, FUNCTION, SMS_SET = "us-east-1", "cds-rr-events", "cds-rr-sms"
PACKAGES = ("domain", "application", "adapters", "infrastructure")


def mask(s) -> str:
    s = re.sub(r"\d{12}", "************", str(s))
    return re.sub(r"user/[\w+=,.@-]+", "user/<iam-user>", s)


def _log(kind, **kw):
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind,
           **{k: (mask(v) if isinstance(v, str) else v) for k, v in kw.items()}}
    with LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row))


def _session():
    import boto3
    return boto3.Session(profile_name=os.environ.get("AWS_PROFILE"))


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for pkg in PACKAGES:
            for f in sorted((ROOT / pkg).rglob("*.py")):
                z.write(f, f.relative_to(ROOT).as_posix())
    return buf.getvalue()


def _try(kind, fn, **kw):
    try:
        out = fn(**kw)
        return out
    except Exception as exc:
        _log(kind + "_REFUSED", error=f"{type(exc).__name__}: {exc}"[:400])
        return None


def deploy():
    sess = _session()
    eum, lam, sns = (sess.client(n, region_name=REGION) for n in ("pinpoint-sms-voice-v2", "lambda", "sns"))
    have = [c["ConfigurationSetName"] for c in eum.describe_configuration_sets()["ConfigurationSets"]]
    if SMS_SET not in have:
        r = _try("SMS_CONFIG_SET", eum.create_configuration_set, ConfigurationSetName=SMS_SET,
                 Tags=[{"Key": "project", "Value": "cds-rental-recovery"}])
        if r:
            _log("SMS_CONFIG_SET_CREATED", name=r["ConfigurationSetName"], arn=r["ConfigurationSetArn"])
    else:
        _log("SMS_CONFIG_SET_EXISTS", name=SMS_SET)
    _try("SNS_CREATE_TOPIC", sns.create_topic, Name="cds-rr-events")
    role_name = os.environ.get("CDS_LAMBDA_ROLE", "")
    role = sess.client("iam").get_role(RoleName=role_name)["Role"]["Arn"]
    code = _zip()
    try:
        lam.get_function(FunctionName=FUNCTION)
        r = lam.update_function_code(FunctionName=FUNCTION, ZipFile=code)
        action = "updated"
    except lam.exceptions.ResourceNotFoundException:
        r = lam.create_function(FunctionName=FUNCTION, Runtime="python3.12", Role=role,
                                Handler="infrastructure.lambda_handlers.events_handler", Code={"ZipFile": code},
                                Timeout=10, MemorySize=128, Tags={"project": "cds-rental-recovery"},
                                Description="cds-rental-recovery: SES and SMS events -> gate decision (one JSON line each)")
        action = "created"
    lam.get_waiter("function_active_v2").wait(FunctionName=FUNCTION)
    f = lam.get_function(FunctionName=FUNCTION)["Configuration"]
    _log("LAMBDA_" + action.upper(), function=f["FunctionName"], arn=f["FunctionArn"], runtime=f["Runtime"],
         handler=f["Handler"], state=f["State"], code_sha256=f["CodeSha256"], code_bytes=f["CodeSize"], role=role)


def _sns(message: dict) -> dict:
    return {"Records": [{"Sns": {"Timestamp": "2026-10-27T11:00:00.000Z", "Message": json.dumps(message)}}]}


def invoke():
    lam = _session().client("lambda", region_name=REGION)
    sms_id = json.loads((ROOT / "docs/live/sms-state.json").read_text())["sends"]["success"]["message_id"]
    canned = {  # documented event shapes; the SMS message id is the real send in sms-log.jsonl
        "sms_delivered": {"eventType": "TEXT_DELIVERED", "destinationPhoneNumber": "+14254147755",
                          "eventTimestamp": 1792998318000, "messageId": sms_id},
        "ses_bounce": {"eventType": "Bounce", "mail": {"messageId": "ses-canned"},
                       "bounce": {"bounceType": "Permanent", "timestamp": "2026-10-27T11:00:00.000Z",
                                  "bouncedRecipients": [{"emailAddress": "bounce@simulator.amazonses.com"}]}},
        "unknown": {"eventType": "TEXT_QUEUED", "destinationPhoneNumber": "+14254147755", "eventTimestamp": 1},
    }
    for name, msg in canned.items():
        r = lam.invoke(FunctionName=FUNCTION, LogType="Tail", Payload=json.dumps(_sns(msg)).encode())
        import base64
        tail = base64.b64decode(r.get("LogResult", "")).decode(errors="replace")
        report = next((ln for ln in tail.splitlines() if ln.startswith("REPORT")), "")
        _log("LAMBDA_INVOKE", case=name, status=r["StatusCode"], function_error=r.get("FunctionError"),
             result=json.loads(r["Payload"].read()), duration=re.findall(r"Duration: ([\d.]+) ms", report)[:1],
             request_id=r["ResponseMetadata"]["RequestId"])
        time.sleep(0.2)


if __name__ == "__main__":
    {"deploy": deploy, "invoke": invoke}[sys.argv[1]]()
