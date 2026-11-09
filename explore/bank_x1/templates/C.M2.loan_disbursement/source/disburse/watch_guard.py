"""WatchGuard: compliance recording for loan-tranche disbursements.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

WatchGuard listens for ``tranche.disbursed`` events on the bus and forwards a
normalised record of each one to the injected compliance hook.
"""

DISBURSED_TOPIC = "tranche.disbursed"


class WatchGuard:
    def __init__(self, bus, compliance_hook):
        self._hook = compliance_hook
        bus.subscribe(DISBURSED_TOPIC, self.on_tranche_disbursed)

    def on_tranche_disbursed(self, event):
        record = {
            "event": "loan.tranche.disbursed",
            "request_id": event["request_id"],
            "loan_id": event["loan_id"],
            "amount_cents": event["amount_cents"],
            "ledger_ref": event["ledger_ref"],
        }
        self._hook(record)
        return record
