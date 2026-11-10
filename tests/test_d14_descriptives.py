"""D14 descriptives: the fixed instrument demonstration is deterministic (first pilot template per
mechanism by sorted id, frozen admission records) and the script refuses an unknown archive."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'analysis'))
import d14_descriptives as D  # noqa: E402


def test_demonstration_is_fixed_and_shows_the_three_witnesses():
    out = D.demonstration()
    assert [out[m]['template_id'] for m in ('M1', 'M2', 'M3')] == \
        ['M1.cold_chain_release', 'M2.loan_disbursement', 'M3.livestream_flags']
    for m in out.values():
        w = m['witnesses']
        assert all(v['oracle_W'] == 0 and v['tests_passed'] for v in w['s_plus'].values())
        assert all(v['oracle_W'] == 1 and v['tests_passed'] for v in w['u_plus'].values())
        assert all(v['oracle_W'] == 0 for v in w['alt_safe'].values())


def test_refuses_an_archive_not_recorded_in_d14(tmp_path):
    f = tmp_path / 'a.tar.gz'
    f.write_bytes(b'x')
    with pytest.raises(SystemExit, match='not the one recorded'):
        D.main(['--calibration-archive', str(f), '--out', str(tmp_path / 'o')])
