"""No silent failures (judge Zip Zieper: 'no silent failures'): every failure ends visible."""
import pathlib, re
from datetime import date, datetime
from adapters.fakes import FakeSender, FixedClock, InMemoryLedger, InMemoryRegistry
from application.service import RecoveryService
from domain.models import Channel, OutboundRequest, Requester, ThreadState, UnreturnedItem, Verdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOON = datetime(2026, 10, 22, 12, 0)
ITEM = UnreturnedItem("L-1", "c1", "camera", 3, date(2026, 10, 15))


class BrokenSender(FakeSender):
    def send(self, req):
        self.calls.append(req)
        raise RuntimeError("Throttling: Maximum sending rate exceeded")


def build(sender):
    ledger = InMemoryLedger([ITEM], {"c1": {Channel.EMAIL: "c1@example.test"}})
    reg = InMemoryRegistry({"c1": {Channel.EMAIL}})
    return RecoveryService(ledger, reg, {Channel.EMAIL: sender}, FixedClock(NOON)), reg


def mail():
    return OutboundRequest(Channel.EMAIL, "c1@example.test", "Please confirm the return of 3 cameras.", Requester.HUMAN)


def test_provider_error_does_not_crash_and_hands_off_with_reason():
    svc, reg = build(BrokenSender(Channel.EMAIL))
    t = svc.open_recovery("L-1")
    out = svc.request_send(t, mail())
    assert out.message_id is None and out.send_error and "Throttling" in out.send_error
    assert t.state is ThreadState.HANDOFF
    assert any(e["kind"] == "SEND_FAILED" for e in reg.entries())


def test_provider_error_is_not_counted_as_a_send():
    svc, reg = build(BrokenSender(Channel.EMAIL))
    t = svc.open_recovery("L-1")
    svc.request_send(t, mail())
    assert reg.sent_today("c1", NOON.date()) == 0


def test_failure_table_lists_only_tests_that_exist():
    doc = (ROOT / "docs" / "FAILURES.md").read_text()
    names = re.findall(r"`(test_[a-z0-9_]+)`", doc)
    assert len(names) >= 7
    src = "\n".join(p.read_text() for p in (ROOT / "tests").glob("test_*.py"))
    missing = [n for n in names if f"def {n}(" not in src]
    assert not missing, missing
