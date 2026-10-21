"""S6: README test count must equal the real pytest result. Usage: python tools/check_readme.py"""
import pathlib, re, subprocess, sys
root = pathlib.Path(__file__).resolve().parent.parent
out = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=root, capture_output=True, text=True).stdout
m = re.search(r"(\d+) passed", out)
claimed = re.search(r"<!--tests-->(\d+)<!--/tests-->", (root / "README.md").read_text())
ok = bool(m and claimed and m[1] == claimed[1] and "failed" not in out)
print(f"pytest passed={m[1] if m else None} README={claimed[1] if claimed else None} -> {'OK' if ok else 'MISMATCH'}")
sys.exit(0 if ok else 1)
