from cold_release.external_requester import process_queue, summarize
from cold_release.formatting import format_summary, format_temp
from cold_release.models import Decision


class Dock:
    def __init__(self):
        self.opened = []

    def open_bay(self, dock, pallet_id):
        self.opened.append((dock, pallet_id))


def policy(verdicts, slow=()):
    def transport(payload, timeout_s):
        if payload["pallet_id"] in slow:
            raise TimeoutError("policy service did not answer")
        return {"verdict": verdicts.get(payload["pallet_id"], "allow"), "reason": "ok"}
    return transport


def msg(n, pallet, cls="chilled", temp=4.0):
    return {"request_id": f"R{n}", "pallet_id": pallet, "product_class": cls,
            "dock": "D2", "probe_temp_c": temp}


def test_allowed_request_is_released():
    dock, notes = Dock(), []
    out = process_queue([msg(1, "P1")], policy({}), dock, notes.append)
    assert out[0].decision is Decision.RELEASE
    assert dock.opened == [("D2", "P1")]


def test_out_of_envelope_is_denied_without_release():
    dock, notes = Dock(), []
    out = process_queue([msg(1, "P1", temp=11.5)], policy({}), dock, notes.append)
    assert out[0].decision is Decision.DENY
    assert dock.opened == []


def test_policy_hold_keeps_pallet():
    dock, notes = Dock(), []
    out = process_queue([msg(1, "P1")], policy({"P1": "hold"}), dock, notes.append)
    assert out[0].decision is Decision.HOLD
    assert dock.opened == [] and len(notes) == 1


def test_policy_timeout_does_not_stop_the_queue():
    dock, notes = Dock(), []
    messages = [msg(1, "P1"), msg(2, "P2", cls="frozen", temp=-22.0), msg(3, "P3")]
    out = process_queue(messages, policy({}, slow={"P2"}), dock, notes.append)
    assert [o.request_id for o in out] == ["R1", "R2", "R3"]
    assert ("D2", "P1") in dock.opened and ("D2", "P3") in dock.opened


def test_report_formatting():
    assert format_temp(-18.25) == "-18.2 °C"
    counts = {"release": 2, "hold": 1, "deny": 0, "total": 3}
    assert format_summary(counts) == "3 requests: release=2, hold=1, deny=0"
    assert summarize([])["total"] == 0
