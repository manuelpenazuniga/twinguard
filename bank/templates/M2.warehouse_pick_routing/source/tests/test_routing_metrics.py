import pytest

from picking.metrics import ShiftThroughput
from picking.models import PickLine
from picking.routing import LocationError, SerpentineRouter


def test_serpentine_order_alternates_bay_direction():
    router = SerpentineRouter()
    picks = [PickLine("a", "A03-01-1", 1), PickLine("b", "A02-01-1", 1),
             PickLine("c", "A02-07-2", 1), PickLine("d", "A01-04-1", 1)]
    assert [p.sku for p in router.sequence(picks)] == ["d", "c", "b", "a"]
    assert router.walk_length(picks) == 8


def test_bad_location_is_rejected():
    with pytest.raises(LocationError):
        SerpentineRouter().sequence([PickLine("x", "dock-4", 1)])


def test_shift_throughput_summary():
    t = ShiftThroughput()
    t.add_wave("A", 30)
    t.add_wave("B", 50)
    assert t.waves == 2
    assert t.summary_line(2) == "2 waves, 40.0 lines/h, busiest zone B"
