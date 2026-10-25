"""Nothing personal or internal in the repo (SPEC non-goal; submission must carry no internal traces)."""
import pathlib, re, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP = {".venv", ".git", ".pytest_cache", "__pycache__"}
PATTERNS = [r"[A-Za-z0-9._%+-]+@(gmail|naver|daum|kakao)\.(com|net)", r"\bprojects/", r"\[\[", r"AKIA[0-9A-Z]{16}", "메인 판단", "발송 전 지울 것", "회신 대기", r"\bJarvis\b"]


def files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (SKIP & set(p.relative_to(ROOT).parts)) and p.suffix in {".py", ".md", ".jsonl", ".json", ".yaml", ".txt", ".html", ".svg"}:
            yield p


def test_no_personal_addresses_internal_links_or_keys():
    hits = []
    for p in files():
        text = p.read_text(errors="ignore")
        for pat in PATTERNS:
            for m in re.finditer(pat, text):
                if p.name == "test_repo_hygiene.py":
                    continue
                hits.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
    assert not hits, hits
