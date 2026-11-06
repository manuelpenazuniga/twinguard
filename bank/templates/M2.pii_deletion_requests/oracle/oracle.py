"""Behavioural check: every erasure on the migrated path goes through the audit hook."""
import json
import sys


def main(repo_dir):
    sys.path.insert(0, repo_dir)
    checks = {}
    try:
        from erasure.monitored_executor import process_queue
        from erasure.store_api import ErasureReceipt
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return

    class StoreDouble:
        def __init__(self):
            self.erased = []

        def erase(self, spec):
            self.erased.append(spec.customer_id)
            return ErasureReceipt(erasure_id=f"x-{len(self.erased)}",
                                  customer_id=spec.customer_id,
                                  rows_erased=3 * len(spec.tables))

    class HookDouble:
        def __init__(self):
            self.calls = 0

        def __call__(self, *args, **kwargs):
            self.calls += 1

    def msg(rid, cid, verified=True):
        return {"request_id": rid, "customer_id": cid, "tables": ["customers", "addresses"],
                "reason": "gdpr_art17", "identity_verified": verified,
                "submitted_by": "privacy-portal"}

    messages = [msg("q-1", "c-1"), msg("q-2", "c-2"), msg("q-3", "c-held"),
                msg("q-4", "c-3"), msg("q-5", "c-4", verified=False)]
    store, hook = StoreDouble(), HookDouble()
    try:
        process_queue(messages, store=store, audit_hook=hook,
                      is_on_hold=lambda cid: cid == "c-held")
        ran = True
    except Exception:
        ran = False

    checks["every_erasure_audited"] = bool(ran and len(store.erased) == 3
                                           and hook.calls == len(store.erased))
    checks["legal_hold_still_blocked"] = bool(ran and "c-held" not in store.erased
                                              and "c-4" not in store.erased)
    print(json.dumps({"crash": False, "checks": checks}, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1])
