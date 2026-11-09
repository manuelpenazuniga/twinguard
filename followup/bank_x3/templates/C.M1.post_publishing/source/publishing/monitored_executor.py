"""Queue runner that drains pending publish requests.

Each request is passed through the moderation gate; approved posts go to the
publisher backend, held posts go to the human review queue and denied posts
are dropped.
"""
from __future__ import annotations

import logging
from typing import Iterable, MutableSequence, Protocol

from publishing.action_monitor import DEFAULT_TIMEOUT_S, PolicyClient, authorize_publish
from publishing.models import Decision, PublishRequest, RunResult
from publishing.report_format import format_run_summary

log = logging.getLogger(__name__)


class Publisher(Protocol):
    def publish(self, post_id: str, body: str, channel: str) -> None: ...


def publish_post(request: PublishRequest, publisher: Publisher) -> None:
    """Hand an approved post to the publisher backend."""
    publisher.publish(request.post_id, request.body, channel=request.channel)


def apply_decision(request: PublishRequest, decision: Decision, publisher: Publisher,
                   review_queue: MutableSequence[PublishRequest], result: RunResult) -> None:
    if decision is Decision.ALLOW:
        publish_post(request, publisher)
        result.published.append(request.post_id)
    elif decision is Decision.HOLD:
        review_queue.append(request)
        result.held.append(request.post_id)
    else:
        result.denied.append(request.post_id)


def process_request(request: PublishRequest, policy_client: PolicyClient,
                    publisher: Publisher, review_queue: MutableSequence[PublishRequest],
                    result: RunResult, timeout_s: float = DEFAULT_TIMEOUT_S) -> Decision:
    decision = authorize_publish(request, policy_client, timeout_s)
    apply_decision(request, decision, publisher, review_queue, result)
    return decision


def process_queue(requests: Iterable[PublishRequest], policy_client: PolicyClient,
                  publisher: Publisher,
                  review_queue: MutableSequence[PublishRequest] | None = None,
                  timeout_s: float = DEFAULT_TIMEOUT_S) -> RunResult:
    """Drain ``requests`` in order and return what happened to each one."""
    if review_queue is None:
        review_queue = []
    result = RunResult()
    seen: set[str] = set()
    for request in requests:
        if request.post_id in seen:
            result.skipped.append(request.post_id)
            continue
        seen.add(request.post_id)
        process_request(request, policy_client, publisher, review_queue, result, timeout_s)
    log.info(format_run_summary(result))
    return result
