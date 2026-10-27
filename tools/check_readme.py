"""S6: the README must match what the repo really has. Usage: python tools/check_readme.py
1. the test count in the README equals the real pytest result;
2. every path in the Evidence column of "What is real and what is simulated" exists;
3. the live-call counts the README states (<!--live:name=N-->) equal the matching event lines in docs/live/*.jsonl."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
_PATHISH = re.compile(r"^[\w./-]+\.(py|md|jsonl|json|png|svg|yaml|txt)$|^[\w-]+/[\w./-]+/?$")


def _evidence_cells(readme: str) -> list:
    sec = re.search(r"## What is real and what is simulated\n(.*?)\n## ", readme, re.S)
    cells = []
    for line in (sec.group(1) if sec else "").splitlines():
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) >= 3 and parts[0] not in ("Part", "---"):
            cells.append(parts[-1])
    return cells


def check_evidence(root: pathlib.Path, readme: str) -> list:
    cells = _evidence_cells(readme)
    if not cells:
        return ["README: table 'What is real and what is simulated' not found"]
    problems = []
    for cell in cells:
        refs = re.findall(r"`([^`]+)`", cell) + re.findall(r"\]\(([^)#]+)\)", cell)
        for ref in refs:
            if _PATHISH.match(ref) and not (root / ref).exists():
                problems.append(f"README Evidence path does not exist: {ref}")
    return problems


def _rows(path: pathlib.Path) -> list:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def live_counts(root: pathlib.Path) -> dict:
    live = root / "docs" / "live"
    ses, sms, bed = _rows(live / "live-log.jsonl"), _rows(live / "sms-log.jsonl"), _rows(live / "bedrock-log.jsonl")
    return {
        "ses_sends": sum(r["kind"] == "SEND" for r in ses),
        "ses_retries": sum(r["kind"] == "RETRY_SEND" and r.get("ses_called") is True for r in ses),
        "sms_sends": sum(r["kind"] in ("SMS_SEND", "SMS_RETRY") and bool(r.get("message_id")) for r in sms),
        "bedrock_calls": sum(r["kind"] == "bedrock_reply" and bool(r.get("usage")) for r in bed),
    }


def check_live_counts(root: pathlib.Path, readme: str) -> list:
    real, problems = live_counts(root), []
    for name, n in real.items():
        m = re.search(rf"<!--live:{name}=(\d+)-->", readme)
        if not m:
            problems.append(f"README does not state {name} (<!--live:{name}=N-->); the log has {n}")
        elif int(m[1]) != n:
            problems.append(f"README says {name}={m[1]}, the log has {n}")
    return problems


def main() -> int:
    readme = (ROOT / "README.md").read_text()
    out = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r"(\d+) passed", out)
    claimed = re.search(r"<!--tests-->(\d+)<!--/tests-->", readme)
    ok = bool(m and claimed and m[1] == claimed[1] and "failed" not in out)
    print(f"pytest passed={m[1] if m else None} README={claimed[1] if claimed else None} -> {'OK' if ok else 'MISMATCH'}")
    problems = check_evidence(ROOT, readme) + check_live_counts(ROOT, readme)
    for p in problems:
        print("MISMATCH:", p)
    print(f"evidence paths and live counts -> {'OK' if not problems else 'MISMATCH'}")
    return 0 if ok and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
