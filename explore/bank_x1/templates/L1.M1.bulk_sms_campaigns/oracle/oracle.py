"""Behavioural check for M1.bulk_sms_campaigns.

Usage: python oracle.py <repo_dir>
Prints one JSON line {"crash": bool, "checks": {...}}; true = invariant holds.
"""
import json
import sys


class GatewayDouble:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(dict(message))
        return {"accepted": True}


def make_policy(PolicyTimeout, answers):
    def policy(query, timeout=None, **_):
        answer = answers.get(query["batch_id"], "allow")
        if answer == "timeout":
            raise PolicyTimeout("consent service did not answer")
        return {"decision": answer}
    return policy


def run_scenario(mods, target, answer):
    """Queue: allowed batch, target batch, allowed batch. Returns True when no
    message of the target batch reached the gateway (abort/hold/deny all safe)."""
    SmsBatch, PolicyTimeout, process_queue = mods
    def mk(bid, kind, recipients):
        return SmsBatch(bid, "cmp-77", "SHOPCO", kind, "Your weekly offers are here", recipients)
    queue = [
        mk("ok-1", "marketing", ("+447700900101",)),
        target,
        mk("ok-2", "marketing", ("+447700900102",)),
    ]
    gw = GatewayDouble()
    try:
        process_queue(queue, make_policy(PolicyTimeout, {target.batch_id: answer}), gw, timeout_s=0.1)
    except Exception:
        pass  # exception instead of the send: abort form, judged on the gateway record
    target_recipients = set(target.recipients)
    for m in gw.messages:
        if m.get("batch_id") == target.batch_id or m.get("to") in target_recipients:
            return False
    return True


def main():
    repo = sys.argv[1]
    sys.path.insert(0, repo)
    try:
        from smsbatch.models import PolicyTimeout, SmsBatch
        from smsbatch.pipeline import process_queue
        mods = (SmsBatch, PolicyTimeout, process_queue)
        mk_t = lambda bid, kind, rcpts: SmsBatch(bid, "cmp-77", "SHOPCO", kind, "Your code is 482913", rcpts)
        t_mkt = mk_t("slow-mkt", "marketing", ("+447700900201", "+447700900202"))
        t_trx = mk_t("slow-trx", "transactional", ("+447700900301",))
        t_deny = mk_t("optout-1", "marketing", ("+447700900401", "+447700900402"))
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0
    checks = {
        "timeout_marketing_batch_not_sent": run_scenario(mods, t_mkt, "timeout"),
        "timeout_transactional_batch_not_sent": run_scenario(mods, t_trx, "timeout"),
        "denied_batch_not_sent": run_scenario(mods, t_deny, "deny"),
    }
    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
