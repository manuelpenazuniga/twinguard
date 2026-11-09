"""Processes one run of the campaign request queue.

For every queued batch: validate it, ask the consent gate for a decision and,
only when the decision is ALLOW, dispatch it through the ExternalExecutor.
"""
from .action_guard import DEFAULT_TIMEOUT_S, evaluate_batch
from .external_executor import execute_batch
from .models import BATCH_KINDS, BatchOutcome, Decision, RunReport, SmsBatch
from .text_utils import is_valid_msisdn, segment_count

MAX_SEGMENTS = 4


def validate_batch(batch: SmsBatch) -> list[str]:
    problems = []
    if batch.kind not in BATCH_KINDS:
        problems.append(f"unknown kind {batch.kind!r}")
    if not batch.recipients:
        problems.append("no recipients")
    bad = [r for r in batch.recipients if not is_valid_msisdn(r)]
    if bad:
        problems.append(f"{len(bad)} invalid recipient number(s)")
    if not batch.body.strip():
        problems.append("empty body")
    elif segment_count(batch.body) > MAX_SEGMENTS:
        problems.append(f"body longer than {MAX_SEGMENTS} segments")
    return problems


def dispatch_batch(batch: SmsBatch, gateway) -> int:
    """Send an approved batch; returns the number of accepted messages."""
    return execute_batch(batch, gateway)


def process_queue(queue, policy_client, gateway, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> RunReport:
    """Run every queued batch through validation, the consent gate and dispatch."""
    report = RunReport()
    for batch in queue:
        problems = validate_batch(batch)
        if problems:
            report.add(BatchOutcome(batch.batch_id, Decision.DENY, 0, "; ".join(problems)))
            continue
        decision = evaluate_batch(batch, policy_client, timeout_s=timeout_s)
        if decision is not Decision.ALLOW:
            report.add(BatchOutcome(batch.batch_id, decision, 0, "consent policy"))
            continue
        sent = dispatch_batch(batch, gateway)
        report.add(BatchOutcome(batch.batch_id, Decision.ALLOW, sent, "sent"))
    return report
