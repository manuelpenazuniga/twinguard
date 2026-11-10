import pytest

from dispatch.external_requester import parse_message, read_requests
from dispatch.models import InvalidRequest


def test_parse_normalises_fields():
    req = parse_message({"request_id": " R9 ", "vehicle_id": "van-9", "route_id": "rt-4",
                         "route_class": "Urban", "depot": "dep-s", "tags": ["b", "a", "b"]})
    assert (req.request_id, req.vehicle_id, req.route_id) == ("R9", "VAN-9", "RT-4")
    assert req.route_class == "urban"
    assert req.tags == ("a", "b")
    assert req.pickup_window == "next-shift"


def test_unknown_route_class_is_invalid():
    with pytest.raises(InvalidRequest):
        parse_message({"request_id": "R1", "vehicle_id": "v", "route_id": "r",
                       "route_class": "offroad", "depot": "d"})


def test_duplicate_ids_are_reported():
    msg = {"request_id": "R1", "vehicle_id": "v", "route_id": "r",
           "route_class": "urban", "depot": "d"}
    items = list(read_requests([msg, dict(msg)]))
    assert items[0][0] == "R1" and not isinstance(items[0][1], InvalidRequest)
    assert isinstance(items[1][1], InvalidRequest)
