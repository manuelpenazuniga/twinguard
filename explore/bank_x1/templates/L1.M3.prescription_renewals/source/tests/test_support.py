import pytest

from renewals.events import EventBus
from renewals.formatting import mask_identifier, review_summary
from renewals.registry import PrescriberRegistry


def test_mask_identifier_keeps_last_digits():
    assert mask_identifier("PT-12345678") == "*******5678"
    assert mask_identifier("12") == "**"


def test_review_summary():
    assert review_summary("RN-9", "prescriber_unknown", "metformin") == \
        "RN-9: Prescriber unknown (metformin)"


def test_registry_rejects_invalid_npi():
    with pytest.raises(ValueError):
        PrescriberRegistry({"RX-1": "12345"})


def test_bus_delivers_in_subscription_order():
    bus, seen = EventBus(), []
    bus.subscribe("t", lambda p: seen.append(("a", p)))
    bus.subscribe("t", lambda p: seen.append(("b", p)))
    bus.publish("t", 1)
    assert seen == [("a", 1), ("b", 1)]
