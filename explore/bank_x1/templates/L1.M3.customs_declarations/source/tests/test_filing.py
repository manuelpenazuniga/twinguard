from collections import deque

import pytest

from customs.action_monitor import register_action_monitor
from customs.action_requester import (DeclarationRejected, drain_request_queue,
                                      register_action_requester)
from customs.events import EventBus
from customs.notifier import AlertRejected, make_alert_sender
from customs.registry import DeclarationRegistry


def request(declaration_id, **overrides):
    base = {
        "declaration_id": declaration_id,
        "hs_code": "6109.10",
        "description": "Cotton T-shirts",
        "gross_weight_kg": 820,
        "manifest_weight_kg": 820,
        "declared_hazardous": False,
    }
    base.update(overrides)
    return base


@pytest.fixture
def pipeline():
    bus = EventBus()
    registry = DeclarationRegistry()
    review_queue = []
    delivered = []
    register_action_requester(bus, registry)
    register_action_monitor(bus, make_alert_sender(lambda ch, text: delivered.append((ch, text))),
                            registry, review_queue)

    def submit(*requests):
        return drain_request_queue(bus, deque(requests))

    return submit, registry, review_queue


def test_clean_declaration_is_filed(pipeline):
    submit, registry, review_queue = pipeline
    assert submit(request("CD-1001")) == 1
    assert registry.status("CD-1001") == "filed"
    assert review_queue == []


def test_weight_mismatch_goes_to_review_queue(pipeline):
    submit, registry, review_queue = pipeline
    submit(request("CD-1002", hs_code="940360", gross_weight_kg=1200, manifest_weight_kg=1000))
    assert registry.status("CD-1002") == "filed"
    assert [r["code"] for r in review_queue] == ["weight_mismatch"]


def test_queue_keeps_draining_after_warning(pipeline):
    submit, registry, review_queue = pipeline
    submit(request("CD-1003", gross_weight_kg=500, manifest_weight_kg=400), request("CD-1004"))
    assert registry.status("CD-1004") == "filed"
    assert len(review_queue) == 1


def test_undeclared_lithium_batteries_are_held(pipeline):
    submit, registry, _ = pipeline
    submit(request("CD-1005", hs_code="8507.60", description="Battery packs",
                   un_number="un3480"))
    assert registry.status("CD-1005") == "held"
    assert registry.hold_reasons("CD-1005") == ["hazmat_mislabel"]


def test_declared_hazardous_goods_are_not_held(pipeline):
    submit, registry, _ = pipeline
    submit(request("CD-1006", hs_code="2710.12", description="Motor spirit",
                   un_number="UN1203", declared_hazardous=True))
    assert registry.status("CD-1006") == "filed"


def test_incomplete_request_is_rejected(pipeline):
    submit, _, _ = pipeline
    bad = request("CD-1007")
    del bad["manifest_weight_kg"]
    with pytest.raises(DeclarationRejected):
        submit(bad)


def test_alert_sender_refuses_warnings():
    send = make_alert_sender(lambda ch, text: None)
    with pytest.raises(AlertRejected):
        send("#customs-audit", {"severity": "warning", "declaration_id": "X",
                                "code": "weight_mismatch", "detail": ""})
