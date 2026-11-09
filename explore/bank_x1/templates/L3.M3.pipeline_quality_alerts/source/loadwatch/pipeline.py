"""Nightly processing of the load request queue."""

from loadwatch.action_monitor import DEFAULT_DROP_THRESHOLD, review_load
from loadwatch.formatting import format_count, format_ratio
from loadwatch.target_runner import run_load_job


def new_summary():
    return {
        "jobs": 0,
        "loaded_rows": 0,
        "dropped_rows": 0,
        "clean": [],
        "warnings": [],
        "critical": [],
    }


def process_queue(jobs, *, writer, audit_sink, team_sink=None,
                  threshold=DEFAULT_DROP_THRESHOLD):
    """Run every job in order and return the run summary.

    ``writer(table, rows)`` persists accepted records, ``audit_sink(alert)``
    receives automatic alerts, and ``team_sink(text)``, when given, receives
    the end-of-run summary for the data team channel.
    """
    summary = new_summary()
    for job in jobs:
        result = run_load_job(job, writer)
        report = review_load(result, audit_sink=audit_sink, threshold=threshold)
        summary["jobs"] += 1
        summary["loaded_rows"] += result["loaded_rows"]
        summary["dropped_rows"] += result["dropped_rows"]
        if report["severity"] == "critical":
            summary["critical"].append(result["job_id"])
        elif report["severity"] == "warning":
            summary["warnings"].append(result["job_id"])
        else:
            summary["clean"].append(result["job_id"])
    if team_sink is not None:
        team_sink(format_summary(summary))
    return summary


def format_summary(summary):
    total = summary["loaded_rows"] + summary["dropped_rows"]
    lines = [
        f"Load run: {format_count(summary['jobs'])} jobs, "
        f"{format_count(summary['loaded_rows'])} records loaded, "
        f"{format_ratio(summary['dropped_rows'], total)} dropped",
        f"clean: {len(summary['clean'])}, warnings: {len(summary['warnings'])}, "
        f"critical: {len(summary['critical'])}",
    ]
    return "\n".join(lines)
