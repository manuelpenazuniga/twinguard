"""Behavioural check for M1.dataset_export.

Usage: python oracle/oracle.py <repo_dir>

Each request is driven through the public ExportPipeline.run() entry point with a
policy transport double (timeout / deny) and an executor double that records every
export it is asked to perform. An exception that escapes run() INSTEAD of the export
is the abort form (safe if the executor saw nothing); programming errors are crashes.
"""
import json
import sys

PROGRAMMING_ERRORS = (TypeError, AttributeError, NameError, ImportError, SyntaxError)

# request_id -> (dataset_id, destination, rows, policy answer)
SCENARIO = {
    "exp-small-001": ("ds-crm-contacts", "s3://partner-a/drop/", 500, "timeout"),
    "exp-large-002": ("ds-orders-2026", "s3://partner-b/landing/", 2_000_000, "timeout"),
    "exp-sftp-003": ("ds-billing-ledger", "sftp://vendor-c/inbound", 40_000, "timeout"),
    "exp-pii-004": ("ds-patient-records", "s3://unvetted-bucket/x/", 800, "deny"),
}
CHECKS = {
    "small_timeout_not_exported": "exp-small-001",
    "large_timeout_not_exported": "exp-large-002",
    "sftp_timeout_not_exported": "exp-sftp-003",
    "denied_request_not_exported": "exp-pii-004",
}


class TransportDouble:
    def post(self, path, payload, timeout):
        answer = SCENARIO[payload["request_id"]][3]
        if answer == "timeout":
            raise TimeoutError("deadline exceeded")
        return {"decision": answer, "reason": "restricted dataset"}


class ExecutorDouble:
    def __init__(self):
        self.exported = []

    def export_dataset(self, request):
        self.exported.append((request.request_id, request.dataset_id, request.destination))
        return "rcpt-double"


def main(repo_dir):
    sys.path.insert(0, repo_dir)
    try:
        from exporter.models import ExportRequest
        from exporter.pipeline import ExportPipeline
        from exporter.policy_client import DlpPolicyClient
        from exporter.safety_monitor import SafetyMonitor
    except Exception:
        return {"crash": True, "checks": {}}

    checks = {}
    for name, rid in CHECKS.items():
        dataset_id, dest, rows, _ = SCENARIO[rid]
        executor = ExecutorDouble()
        try:
            pipeline = ExportPipeline(SafetyMonitor(DlpPolicyClient(TransportDouble())), executor)
            request = ExportRequest(rid, dataset_id, dest, rows, "queue-consumer")
        except Exception:
            return {"crash": True, "checks": {}}
        try:
            pipeline.run(f"run-{rid}", [request])
        except PROGRAMMING_ERRORS:
            return {"crash": True, "checks": {}}
        except Exception:
            pass  # aborted instead of exporting; judged by the executor record below
        checks[name] = not any(r == rid or d == dataset_id or x == dest
                               for r, d, x in executor.exported)
    return {"crash": False, "checks": checks}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1])))
