"""Execution of load jobs taken from the load request queue.

A job names a target table and carries a batch of records. Records that fail
validation are dropped; the rest are handed to the table writer in one call.
"""

REQUIRED_FIELDS = ("record_id", "event_time", "amount")


def validate_row(row):
    """Return a rejection reason for ``row``, or None when it can be loaded."""
    if not isinstance(row, dict):
        return "not_a_record"
    for field in REQUIRED_FIELDS:
        if row.get(field) in (None, ""):
            return f"missing_{field}"
    if not isinstance(row["amount"], (int, float)) or isinstance(row["amount"], bool):
        return "bad_amount"
    return None


def run_load_job(job, writer):
    """Validate the job's records, write the accepted ones, return the outcome."""
    rows = job.get("rows", [])
    accepted = []
    rejections = {}
    for row in rows:
        reason = validate_row(row)
        if reason is None:
            accepted.append(row)
        else:
            rejections[reason] = rejections.get(reason, 0) + 1
    if accepted:
        writer(job["table"], accepted)
    return {
        "job_id": job["job_id"],
        "table": job["table"],
        "submitted_by": job.get("submitted_by", "unknown"),
        "source_rows": len(rows),
        "loaded_rows": len(accepted),
        "dropped_rows": len(rows) - len(accepted),
        "rejections": rejections,
    }
