"""Local web screen for the outbound gate. Standard library only. Run: python -m infrastructure.web"""
from __future__ import annotations

import sys
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlparse

from domain.models import ThreadState, Verdict
from .demo_scenario import DEFAULT_REPLY, Story, Step, build_optout_story, build_story

CSS = """
:root{--bg:#f4f5f7;--card:#fff;--ink:#191f28;--sub:#4e5968;--line:#e5e8eb;--brand:#3182f6;
--pass:#0b7a3e;--pass-bg:#e3f5ea;--hold:#8a5a00;--hold-bg:#fff2d6;--block:#c0222d;--block-bg:#fde8ea;--appr:#4527a0;--appr-bg:#ece7fb}
@media (prefers-color-scheme:dark){:root{--bg:#101216;--card:#1b1e24;--ink:#f2f4f6;--sub:#a9b1bd;--line:#2c313a;--brand:#5b9bff;
--pass:#5fd394;--pass-bg:#10301f;--hold:#ffc857;--hold-bg:#3a2d0c;--block:#ff8a92;--block-bg:#3d1519;--appr:#b9a4ff;--appr-bg:#291f4d}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:560px;margin:0 auto;padding:16px 16px 24px}
.top{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px}
.tag{font-size:16px;font-weight:700;color:var(--sub)}.syn{background:var(--hold-bg);color:var(--hold);padding:4px 10px;border-radius:999px;font-weight:700;font-size:16px}
.bar{display:flex;gap:4px;margin:0 0 20px}.bar i{flex:1;height:6px;border-radius:3px;background:var(--line)}.bar i.on{background:var(--brand)}
h1{font-size:26px;line-height:1.3;margin:0 0 8px;letter-spacing:-.01em}p.lead{margin:0 0 20px;color:var(--sub)}
.card{background:var(--card);border-radius:20px;padding:20px;margin-bottom:12px;overflow-wrap:anywhere}
.vp{display:inline-flex;align-items:center;gap:8px;font-weight:800;font-size:22px;padding:8px 16px;border-radius:14px;margin-bottom:12px}
.v-pass{background:var(--pass-bg);color:var(--pass)}.v-hold{background:var(--hold-bg);color:var(--hold)}
.v-block{background:var(--block-bg);color:var(--block)}.v-approval{background:var(--appr-bg);color:var(--appr)}
.reason{font-size:18px;font-weight:700;margin:0 0 12px}
dl{margin:0;display:grid;grid-template-columns:110px 1fr;gap:8px 12px}dt{color:var(--sub)}dd{margin:0;font-weight:600}
.msg{background:var(--bg);border-radius:12px;padding:12px;margin-top:12px;color:var(--ink)}
.state{display:flex;gap:8px;flex-wrap:wrap}.chip{padding:6px 12px;border-radius:999px;background:var(--bg);font-weight:700}
.log{list-style:none;margin:0;padding:0}.log li{display:flex;gap:10px;align-items:center;padding:8px 0;border-top:1px solid var(--line)}
.log li:first-child{border-top:0}.dot{font-weight:800;min-width:112px;white-space:nowrap;padding:2px 8px;border-radius:8px;text-align:center;font-size:16px}
h2{font-size:18px;margin:0 0 8px}
textarea{width:100%;font:inherit;padding:12px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--ink);min-height:84px}
.cta{position:sticky;bottom:0;background:linear-gradient(transparent,var(--bg) 40%);padding:24px 16px 16px}
.cta .in{max-width:560px;margin:0 auto}
a.primary,button.primary{display:block;width:100%;text-align:center;background:var(--brand);color:#fff;font-weight:700;font-size:18px;line-height:1;font-family:inherit;padding:18px;border-radius:16px;border:0;text-decoration:none}
button.secondary,a.link{display:inline-block;margin-top:8px;font-weight:700;font-size:16px;line-height:1;font-family:inherit;cursor:pointer;color:var(--brand);background:none;border:0;padding:10px 0;text-decoration:none}
"""

ICON = {Verdict.PASS: "PASS", Verdict.HOLD: "HOLD", Verdict.BLOCK: "BLOCK", Verdict.APPROVAL: "APPROVAL"}
REASON = {"ok": "All checks passed", "daily_cap": "Daily cap reached (2 per day)", "quiet_hours": "Quiet hours (21:00 to 08:00)",
          "needs_approval": "Money or legal wording needs a person", "opt_out": "Customer opted out",
          "no_consent": "No consent for this channel", "address_blocked": "Address stopped after a bounce"}
CTA_MAIN = {Verdict.PASS: "Sent", Verdict.HOLD: "Held until morning", Verdict.BLOCK: "Not sent", Verdict.APPROVAL: "Waiting for a person"}


def _verdict_card(st: Step) -> str:
    v = st.verdict
    rows = [("Channel", v.channel.value), ("Requested by", "AI agent" if v.requested_by.value == "AGENT" else "Person"),
            ("Time", st.at.strftime("%b %d, %H:%M"))]
    if v.release_at:
        rows.append(("Releases", v.release_at.strftime("%b %d, %H:%M")))
    rows.append(("Sender calls", str(st.sender_calls_delta)))
    dl = "".join(f"<dt>{escape(a)}</dt><dd>{escape(b)}</dd>" for a, b in rows)
    msg = f'<div class="msg">{escape(st.request.text)}</div>' if st.request else ""
    return (f'<section class="card"><div class="vp v-{v.verdict.value.lower()}">{ICON[v.verdict]}</div>'
            f'<p class="reason">{escape(REASON.get(v.reason, v.reason))}</p><dl>{dl}</dl>{msg}</section>')


def _event_card(st: Step) -> str:
    e, d = st.event, st.decision
    rows = [("Channel", e.channel.value), ("Next step", d.note)]
    if d.suggest_channel:
        rows.append(("Switch to", d.suggest_channel.value))
    if d.nudge_after_hours:
        rows.append(("Nudge in", f"{d.nudge_after_hours} hours"))
    if d.handoff:
        rows.append(("Hand-off", "A person takes over"))
    dl = "".join(f"<dt>{escape(a)}</dt><dd>{escape(b)}</dd>" for a, b in rows)
    return f'<section class="card"><div class="vp v-pass" style="background:var(--bg);color:var(--ink)">{e.kind.value}</div><dl>{dl}</dl></section>'


def _reading_card(st: Step, story: Story) -> str:
    r, c = st.reading, st.comparison
    ok = c.matches
    label = "MATCHES LEDGER" if ok else "NEEDS A PERSON"
    cls = "v-pass" if ok else "v-hold"
    rows = [("Quantity", str(r.quantity) if r.quantity is not None else "not found"),
            ("Return date", r.return_date.strftime("%b %d") if r.return_date else "not found"),
            ("Confidence", f"{int(r.confidence * 100)}%"), ("Ledger says", "3 units"), ("Result", c.reason.replace("_", " "))]
    dl = "".join(f"<dt>{escape(a)}</dt><dd>{escape(b)}</dd>" for a, b in rows)
    note = f'<p class="lead" style="margin:12px 0 0">{escape(st.note)}</p>' if st.note else ""
    form = (f'<form method="get"><input type="hidden" name="s" value="{story.steps.index(st)}">'
            f'<input type="hidden" name="case" value="main"><h2>Try your own reply</h2>'
            f'<textarea name="reply" aria-label="Customer reply">{escape(story.reply_text)}</textarea>'
            f'<button class="secondary" type="submit">Read this reply</button></form>')
    return (f'<section class="card"><div class="vp {cls}">{label}</div><dl>{dl}</dl>{note}</section>'
            f'<section class="card">{form}</section>')


def _log(story: Story, upto: int) -> str:
    items = []
    for st in story.steps[:upto]:
        if st.verdict:
            v = st.verdict.verdict
            items.append(f'<li><span class="dot v-{v.value.lower()}">{ICON[v]}</span><span>{escape(st.title)}</span></li>')
    if not items:
        return ""
    return f'<section class="card"><h2>Gate log</h2><ul class="log">{"".join(items)}</ul></section>'


def render_page(story: Story, i: int, reply: str = None) -> str:
    st = story.steps[i]
    n = len(story.steps)
    bar = "".join(f'<i class="{"on" if k <= i else ""}"></i>' for k in range(n))
    body = ""
    if st.verdict:
        body += _verdict_card(st)
    if st.event:
        body += _event_card(st)
    if st.reading:
        body += _reading_card(st, story)
    ledger = f"{len(st.ledger_rows)} row" + ("" if len(st.ledger_rows) == 1 else "s")
    if st.ledger_rows:
        p = st.ledger_rows[0]
        ledger += f" ({p.quantity} units back {p.return_date.strftime('%b %d')})"
    chips = (f'<div class="state"><span class="chip">Thread {st.thread_state.value}</span>'
             f'<span class="chip">SMS sent {st.sms_sent}</span><span class="chip">Email sent {st.email_sent}</span>'
             f'<span class="chip">Ledger {escape(ledger)}</span></div>')
    if st.thread_state is ThreadState.HANDOFF and st.handoff_reason:
        chips += f'<p class="lead" style="margin:12px 0 0">Hand-off reason: {escape(st.handoff_reason.replace("_", " "))}</p>'
    body += f'<section class="card">{chips}</section>' + _log(story, i)
    case = "optout" if story.name == "Customer opted out" else "main"
    last = i == n - 1
    if not last:
        cta = f'<a class="primary" href="/?case={case}&s={i + 1}&reply={quote(story.reply_text)}">Next</a>'
    else:
        other = "optout" if case == "main" else "main"
        cta = (f'<a class="primary" href="/?case={other}&s=0">{"See the opt-out ending" if case == "main" else "Back to the main case"}</a>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Outbound Gate</title><style>{CSS}</style></head><body><main>'
            f'<div class="top"><span class="tag">Step {i + 1} of {n}</span><span class="syn">Synthetic data</span></div>'
            f'<div class="bar">{bar}</div><h1>{escape(st.title)}</h1><p class="lead">{escape(st.body)}</p>{body}</main>'
            f'<div class="cta"><div class="in">{cta}</div></div></body></html>')


def make_story(case: str, reply: str) -> Story:
    return build_optout_story() if case == "optout" else build_story(reply)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        case = q.get("case", ["main"])[0]
        reply = (q.get("reply", [DEFAULT_REPLY])[0] or DEFAULT_REPLY)[:300]
        story = make_story(case, reply)
        try:
            i = max(0, min(int(q.get("s", ["0"])[0]), len(story.steps) - 1))
        except ValueError:
            i = 0
        data = render_page(story, i).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def main(port: int = 8765) -> None:
    print(f"Outbound gate screen on http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
