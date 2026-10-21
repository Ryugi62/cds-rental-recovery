"""Capture every gate-screen step at 390px and assert no horizontal scroll. Needs playwright (not a runtime dep).
Usage: python tools/capture.py   (starts the local server itself)"""
import subprocess, sys, time, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screens"
PORT = 8791
CASES = {"main": 11, "optout": 4}


def main():
    srv = subprocess.Popen([sys.executable, "-m", "infrastructure.web", str(PORT)], cwd=ROOT, stdout=subprocess.DEVNULL)
    time.sleep(1.0)
    bad = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 390, "height": 844})
            for case, n in CASES.items():
                for s in range(n):
                    pg.goto(f"http://127.0.0.1:{PORT}/?case={case}&s={s}")
                    w = pg.evaluate("document.documentElement.scrollWidth")
                    small = pg.evaluate("Math.min(...[...document.querySelectorAll('main *')].filter(e=>e.childNodes.length&&[...e.childNodes].some(n=>n.nodeType==3&&n.textContent.trim())).map(e=>parseFloat(getComputedStyle(e).fontSize)))")
                    if w > 390 or small < 16:
                        bad.append((case, s, w, small))
                    pg.add_style_tag(content='.cta{position:static!important}')  # full-page capture: show the button in flow
                    pg.screenshot(path=str(OUT / f"{case}-{s:02d}.png"), full_page=True)
            b.close()
    finally:
        srv.terminate()
    print("overflow/small-font violations:", bad)
    sys.exit(1 if bad else 0)


main()
