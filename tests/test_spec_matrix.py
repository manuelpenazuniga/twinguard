"""Tests for bank/make_spec.py (WP3)."""
import copy
from collections import Counter
from pathlib import Path

import pytest

from bank import make_spec as ms

TOML = Path(__file__).resolve().parents[1] / 'bank' / 'sectors.toml'


@pytest.fixture(scope='module')
def spec():
    return ms.load_sectors(TOML)


def test_shape_and_balance(spec):
    rows = ms.build_rows(*spec)
    conf = [r for r in rows if r['split'] == 'confirmatory']
    assert len(conf) == 30 and len(rows) == 36
    assert Counter(r['mechanism'] for r in conf) == {'M1': 10, 'M2': 10, 'M3': 10}
    assert len({r['subdomain'] for r in rows}) == 36
    assert len({r['template_id'] for r in rows}) == 36


def test_latin_square_styles(spec):
    conf = [r for r in ms.build_rows(*spec) if r['split'] == 'confirmatory']
    for fam in {r['family'] for r in conf}:
        assert {r['style'] for r in conf if r['family'] == fam} == set(ms.STYLES)
    for m in ms.MECHANISMS:  # each style appears 3 or 4 times per mechanism
        counts = Counter(r['style'] for r in conf if r['mechanism'] == m)
        assert sorted(counts.values()) in ([3, 3, 4],)


def test_pilot_two_styles_per_mechanism(spec):
    pilot = [r for r in ms.build_rows(*spec) if r['split'] == 'pilot']
    for m in ms.MECHANISMS:
        assert len({r['style'] for r in pilot if r['mechanism'] == m}) == 2


def test_deterministic_and_seed_sensitive(spec):
    a = ms.to_csv(ms.build_rows(*spec, seed=1))
    assert a == ms.to_csv(ms.build_rows(*spec, seed=1))
    assert a != ms.to_csv(ms.build_rows(*spec, seed=2))


def test_rejects_repeated_subdomain(spec):
    sectors, ids = copy.deepcopy(spec)
    sectors[1]['M1']['subdomain'] = sectors[0]['M1']['subdomain']
    with pytest.raises(ms.SpecError):
        ms.build_rows(sectors, ids)


def test_no_experiment_vocabulary_in_seeds(spec):
    banned = ('ai ', 'agent', 'llm', 'model', 'experiment', 'framing', 'twin')
    for r in ms.build_rows(*spec):
        text = f" {r['scenario_seed']} {r['actor_identifier']} {r['monitor_identifier']} ".lower()
        assert not any(b in text for b in banned), r['template_id']
