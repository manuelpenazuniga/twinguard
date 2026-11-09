from pricing.audit import ControlMonitor
from pricing.catalog import PriceCatalog
from pricing.models import PriceRequest
from pricing.runner import TargetRunner


def make_runner(prices):
    catalog = PriceCatalog(prices)
    return catalog, TargetRunner(catalog, ControlMonitor([]))


def test_set_price_keeps_exact_cents():
    catalog, runner = make_runner({"TSHIRT-M": 2500, "MUG-01": 1200})
    report = runner.run_batch([
        PriceRequest("r1", "TSHIRT-M", "set", 1999),
        PriceRequest("r2", "MUG-01", "set", 1129),
    ])
    assert report.applied == ["r1", "r2"]
    assert catalog.get_cents("TSHIRT-M") == 1999
    assert catalog.get_cents("MUG-01") == 1129


def test_percentage_adjustment():
    catalog, runner = make_runner({"HOODIE-L": 2000})
    report = runner.run_batch([PriceRequest("r1", "HOODIE-L", "adjust", -10)])
    assert report.applied == ["r1"]
    assert catalog.get_cents("HOODIE-L") == 1800


def test_unchanged_price_counts_as_applied():
    catalog, runner = make_runner({"CAP-01": 1500})
    report = runner.run_batch([PriceRequest("r1", "CAP-01", "set", 1500)])
    assert report.applied == ["r1"]
    assert catalog.get_cents("CAP-01") == 1500


def test_price_below_floor_is_rejected():
    catalog, runner = make_runner({"SOCKS-3": 900, "BAG-02": 3000})
    report = runner.run_batch([
        PriceRequest("r1", "SOCKS-3", "set", 40),
        PriceRequest("r2", "BAG-02", "adjust", 5),
    ])
    assert report.rejected == ["r1"]
    assert report.applied == ["r2"]
    assert catalog.get_cents("SOCKS-3") == 900
    assert catalog.get_cents("BAG-02") == 3150
