"""Clean Architecture: no reverse imports (SPEC section 6)."""
import pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
ORDER = ["domain", "application", "adapters", "infrastructure"]


def imports(path):
    return re.findall(r"^\s*(?:from|import)\s+([a-zA-Z_][\w\.]*)", path.read_text(), re.M)


def test_no_reverse_imports():
    for i, layer in enumerate(ORDER):
        outer = set(ORDER[i + 1:])
        for f in (ROOT / layer).glob("*.py"):
            bad = [m for m in imports(f) if m.split(".")[0] in outer]
            assert not bad, f"{f.name} imports outward layer: {bad}"


def test_domain_has_no_sdk_or_io():
    banned = {"boto3", "botocore", "requests", "http", "socket", "os", "subprocess", "sqlite3", "json", "email"}
    for f in (ROOT / "domain").glob("*.py"):
        assert not [m for m in imports(f) if m.split(".")[0] in banned], f.name


def test_domain_never_reads_the_clock():
    for f in (ROOT / "domain").glob("*.py"):
        assert not re.search(r"\.(now|today|utcnow)\(", f.read_text()), f.name
