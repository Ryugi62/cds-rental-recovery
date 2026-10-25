"""IaC entry points (template.yaml): SNS -> event decision log, SNS -> reply reading. No AWS calls."""
import json, pathlib
from infrastructure.lambda_handlers import events_handler, inbound_handler

ROOT = pathlib.Path(__file__).resolve().parent.parent


def sns_records(*messages):
    return {"Records": [{"EventSource": "aws:sns", "Sns": {"Message": json.dumps(m),
                                                          "Timestamp": "2026-10-26T03:05:00.000Z"}} for m in messages]}


BOUNCE = {"eventType": "Bounce", "mail": {"messageId": "m1"},
          "bounce": {"bounceType": "Permanent", "bouncedRecipients": [{"emailAddress": "bounce@simulator.amazonses.com"}],
                     "timestamp": "2026-10-26T03:05:00.000Z"}}
COMPLAINT = {"eventType": "Complaint", "mail": {"messageId": "m2"},
             "complaint": {"complainedRecipients": [{"emailAddress": "complaint@simulator.amazonses.com"}],
                           "timestamp": "2026-10-26T03:05:00.000Z"}}
SMS_BLOCKED = {"eventType": "TEXT_BLOCKED", "destinationPhoneNumber": "+10000000001", "eventTimestamp": 1761447900000,
            "messageId": "s1"}
REPLY = ("From: owner@example.test\r\nSubject: Re: return\r\nContent-Type: text/plain\r\n\r\n"
         "I'll bring back 3 on Thursday\r\n")


def test_events_handler_turns_ses_and_sms_events_into_decisions():
    out = events_handler(sns_records(BOUNCE, COMPLAINT, SMS_BLOCKED), None)
    kinds = [(o["kind"], o["block_address"], o["opt_out_customer"]) for o in out["decisions"]]
    assert ("BOUNCE", True, False) in kinds and ("OPT_OUT", False, True) in kinds
    assert sum(1 for o in out["decisions"] if o["channel"] == "SMS") == 1


def test_events_handler_reports_unknown_messages_instead_of_dropping_them():
    out = events_handler(sns_records({"eventType": "Open", "mail": {"messageId": "m3"}}), None)
    assert out["decisions"] == [] and out["ignored"] == 1


def test_inbound_handler_reads_quantity_and_date():
    note = {"notificationType": "Received", "mail": {"source": "owner@example.test", "messageId": "in-1"}, "content": REPLY}
    out = inbound_handler(sns_records(note), None)
    r = out["readings"][0]
    assert r["quantity"] == 3 and r["return_date"] == "2026-10-29" and r["confidence"] >= 0.8


def test_template_wires_both_channels_and_both_handlers():
    t = (ROOT / "template.yaml").read_text()
    for needle in ("AWS::SES::ConfigurationSet", "AWS::SES::ConfigurationSetEventDestination", "AWS::SMSVOICE::ConfigurationSet",
                   "AWS::SES::ReceiptRule", "infrastructure.lambda_handlers.events_handler",
                   "infrastructure.lambda_handlers.inbound_handler", "AWS::SNS::Topic"):
        assert needle in t, needle


def test_template_passes_cfn_lint_when_installed():
    import shutil, subprocess, sys
    exe = pathlib.Path(sys.executable).parent / "cfn-lint"
    if not exe.exists():
        import pytest
        pytest.skip("cfn-lint not installed")
    r = subprocess.run([str(exe), str(ROOT / "template.yaml")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_agents_guide_has_preflight_deploy_and_post_checks_in_order():
    g = (ROOT / "AGENTS.md").read_text()
    i, j, k = g.index("## 1. Preflight"), g.index("## 2. Deploy"), g.index("## 3. Post-deploy")
    assert i < j < k and "sam deploy" in g and "cfn-lint template.yaml" in g
