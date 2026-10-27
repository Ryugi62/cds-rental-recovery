"""S6: tools/check_readme.py also checks the README's Evidence paths and its claimed live-call counts against docs/live logs."""
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_readme", ROOT / "tools" / "check_readme.py")
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

README = (ROOT / "README.md").read_text()


def make_root(tmp_path, ses=4, retry=2, sms=3, bedrock=6):
    live = tmp_path / "docs" / "live"
    live.mkdir(parents=True)
    rows = [{"kind": "SEND"}] * ses + [{"kind": "RETRY_SEND", "ses_called": True}] * retry + [{"kind": "RETRY_SEND", "ses_called": False}]
    (live / "live-log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    rows = [{"kind": "SMS_SEND", "message_id": "m"}] * sms + [{"kind": "SMS_RETRY", "message_id": None}]
    (live / "sms-log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    rows = [{"kind": "bedrock_reply", "usage": {"totalTokens": 1}}] * bedrock + [{"kind": "bedrock_reply", "usage": {}}, {"kind": "bedrock_run_summary"}]
    (live / "bedrock-log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_path


def test_real_readme_passes_against_the_real_repo():
    assert cr.check_evidence(ROOT, README) == []
    assert cr.check_live_counts(ROOT, README) == []


def test_missing_evidence_path_is_reported():
    bad = README.replace("`docs/live/live-log.jsonl`", "`docs/live/no-such-log.jsonl`", 1)
    problems = cr.check_evidence(ROOT, bad)
    assert any("no-such-log.jsonl" in p for p in problems)


def test_claimed_count_that_differs_from_the_log_is_reported(tmp_path):
    root = make_root(tmp_path, bedrock=5)  # README claims 6 Bedrock calls
    problems = cr.check_live_counts(root, README)
    assert any("bedrock_calls" in p and "5" in p for p in problems)
    assert cr.check_live_counts(make_root(tmp_path / "ok"), README) == []


def test_readme_that_stops_stating_counts_fails():
    stripped = README.replace("<!--live:sms_sends=3-->", "")
    assert any("sms_sends" in p for p in cr.check_live_counts(ROOT, stripped))
