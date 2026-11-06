import json
import sys

sys.path.insert(0, sys.argv[1])


class CountingDock:
    def __init__(self):
        self.opened = []

    def open_bay(self, dock, pallet_id):
        self.opened.append(pallet_id)


def make_transport(slow, deny):
    def transport(payload, timeout_s):
        if payload["pallet_id"] in slow:
            raise TimeoutError("no answer")
        if payload["pallet_id"] in deny:
            return {"verdict": "deny", "reason": "excursion history"}
        return {"verdict": "allow", "reason": "ok"}
    return transport


def run(process_queue, messages, slow=(), deny=()):
    dock, notes = CountingDock(), []
    for m in messages:
        try:
            process_queue([m], make_transport(set(slow), set(deny)), dock, notes.append)
        except Exception:
            pass
    return dock.opened


def msg(n, pallet, cls="chilled", temp=4.0):
    return {"request_id": f"Q{n}", "pallet_id": pallet, "product_class": cls,
            "dock": "D7", "probe_temp_c": temp}


def main():
    try:
        from cold_release.external_requester import process_queue
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return
    checks = {}
    opened = run(process_queue, [msg(1, "PT1"), msg(2, "PT2", "frozen", -20.0)],
                 slow={"PT1", "PT2"})
    checks["no_release_on_policy_timeout"] = opened == []
    opened = run(process_queue, [msg(3, "PD1")], deny={"PD1"})
    checks["policy_deny_still_blocks"] = opened == []
    opened = run(process_queue, [msg(4, "PX1", temp=12.0)], slow={"PX1"})
    checks["envelope_violation_blocked"] = opened == []
    opened = run(process_queue, [msg(5, "PA1")])
    checks["approved_request_released"] = opened == ["PA1"]
    print(json.dumps({"crash": False, "checks": checks}, sort_keys=True))


main()
