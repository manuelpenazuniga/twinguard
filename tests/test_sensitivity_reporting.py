"""Frozen sensitivity (D9): reproduce certifies only a reproduced sensitivity, and the tables
follow the D9 reporting rule (Astra review of the sensitivity, 2026-11-09)."""
import csv
import importlib.util
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from runner import analyze as AN  # noqa: E402
from runner import runner as R  # noqa: E402

ANALYSIS = ROOT / 'twinguard' / 'twinguard_analysis.py'
COMMIT = 'abcdef1234567890' * 2 + 'abcdef12'
FROZEN_SCRIPT = f'/tmp/twinguard_frozen_{COMMIT[:12]}_q1/twinguard/twinguard_analysis.py'


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CLI = load('tg_cli_sens', 'resource/cli.py')
TB = load('tg_tables_sens', 'resource/tables.py')


def fz_of(runs, fam, S=1):
    return {'design': {'S': S, 'sensitivity': {
        'exclude_families': [fam], 'K': 27,
        'templates_dropped': sorted({r['template_id'] for r in runs if r['family'] == fam})}}}


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    """A results directory with VARIABLE outcomes: primary run, frozen sensitivity, record."""
    runs = R.schedule(ROOT / 'bank' / 'templates', ROOT / 'bank' / 'spec_matrix.csv',
                      'confirmatory', 1, 20261107)
    rng = random.Random(11)
    res = tmp_path_factory.mktemp('res')
    with open(res / 'runs.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=R.COLUMNS)
        w.writeheader()
        for r in runs:
            w.writerow({**{k: r.get(k, '') for k in R.COLUMNS}, 'status': 'patch',
                        'W': int(rng.random() < (0.45 if r['framing'] == 'A' else 0.3)),
                        'F': 1, 'M': 1, 'crash': 0, 'model_id': R.MODEL_ID,
                        'model_revision': 'v', 'harness_commit': 'c', 'oracle_commit': 'c',
                        'environment_id': 'e'})
    fam = runs[0]['family']
    fz = fz_of(runs, fam)
    cmd = [sys.executable, str(ANALYSIS), str(res / 'runs.csv'), '--replicates', '1',
           '--output', str(res / 'analysis_output.json')]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-2000:]
    rec = AN.run_sensitivity(fz['design']['sensitivity'], res / 'runs.csv', 1, res)
    assert rec.get('rc') == 0, rec
    h = {'cmd': cmd[1:], 'rc': 0, 'sensitivity': rec}
    (res / 'analysis_hashes.json').write_text(json.dumps(h))
    blocks = [{'family': f, 'state': 'complete', 'scheduled': 36, 'closed_out': 0}
              for f in sorted({x['family'] for x in runs})]
    (res / 'truncation_report.json').write_text(json.dumps(
        {'K_scheduled': 30, 'K_in_complete_blocks': 30, 'closed_out_runs': 0, 'analysis_flag': '',
         'exploratory_required': False, 'blocks': blocks}))
    return {'res': res, 'fz': fz, 'h': h, 'runs': runs, 'fam': fam}


def copy(base, tmp_path):
    d = tmp_path / 'res'
    shutil.copytree(base['res'], d)
    return d


def test_reproduce_certifies_only_a_reproduced_sensitivity(base, tmp_path):
    res, fz, h = copy(base, tmp_path), base['fz'], base['h']
    ok = CLI.check_sensitivity(res, fz, h, 'runs.csv')
    assert ok['reproduced'] and ok['cmd_matches_freeze'] and ok['input_rederived_identical']
    # the recorded state must be the one the primary's outcome implies
    skipped = {'skipped': 'primary analysis failed'}
    assert not CLI.check_sensitivity(res, fz, {**h, 'sensitivity': skipped}, 'runs.csv')['reproduced']
    assert CLI.check_sensitivity(res, fz, {**h, 'rc': 1, 'sensitivity': skipped}, 'runs.csv')['reproduced']
    assert not CLI.check_sensitivity(res, fz, {**h, 'rc': 1}, 'runs.csv')['reproduced']
    pending = {'pending': 'runs after the primary seal'}
    assert not CLI.check_sensitivity(res, fz, {**h, 'sensitivity': pending}, 'runs.csv')['reproduced']
    assert not CLI.check_sensitivity(res, fz, {**h, 'sensitivity': None}, 'runs.csv')['reproduced']
    # the recorded command must be the frozen one (no extra seed/bootstrap, frozen S and K)
    extra = {**h['sensitivity'], 'cmd': h['sensitivity']['cmd'] + ['--seed', '1']}
    rep = CLI.check_sensitivity(res, fz, {**h, 'sensitivity': extra}, 'runs.csv')
    assert rep['cmd_matches_freeze'] is False and not rep['reproduced']
    # a different frozen S: the re-run follows the freeze and does not reproduce the record
    assert not CLI.check_sensitivity(res, {'design': {**fz['design'], 'S': 2}}, h, 'runs.csv')['reproduced']
    # a changed published output is caught
    o = json.loads((res / 'analysis_sensitivity.json').read_text())
    o['H1_PRIMARY_W_A_minus_N']['HC3_95']['estimate'] += 0.01
    (res / 'analysis_sensitivity.json').write_text(json.dumps(o))
    assert not CLI.check_sensitivity(res, fz, h, 'runs.csv')['reproduced']
    # a sensitivity recorded but not frozen
    assert not CLI.check_sensitivity(res, {'design': {'S': 1}}, h, 'runs.csv')['reproduced']


def test_reproduce_recorded_failure_must_fail_the_same_way(base, tmp_path):
    res = copy(base, tmp_path)
    for n in ('analysis_sensitivity.json', 'analysis_sensitivity.txt', 'analysis_sensitivity_input.csv'):
        (res / n).unlink()
    fz2 = {'design': {**base['fz']['design'], 'S': 2}}         # S=1 data: the analysis fails
    rec = AN.run_sensitivity(fz2['design']['sensitivity'], res / 'runs.csv', 2, res)
    assert rec.get('rc') not in (0, None) and not (res / 'analysis_sensitivity.json').exists()
    h = {**base['h'], 'sensitivity': rec}
    assert CLI.check_sensitivity(res, fz2, h, 'runs.csv')['reproduced']
    txt = res / 'analysis_sensitivity.txt'
    txt.write_text(txt.read_text() + '\nanother failure')        # same rc, different failure
    assert not CLI.check_sensitivity(res, fz2, h, 'runs.csv')['reproduced']
    # a recorded error does not reproduce against a run that succeeds
    res2 = copy(base, tmp_path / 'b')
    h2 = {**base['h'], 'sensitivity': {'cmd': None, 'stage': 'derive', 'error_type': 'ValueError',
                                       'error': 'ValueError: sensitivity input does not match the '
                                       'freeze', 'env': {}}}
    assert not CLI.check_sensitivity(res2, base['fz'], h2, 'runs.csv')['reproduced']
    # an unstructured error record is refused
    h3 = {**base['h'], 'sensitivity': {'cmd': None, 'error': 'ValueError: x'}}
    assert not CLI.check_sensitivity(res2, base['fz'], h3, 'runs.csv')['reproduced']


def test_reproduce_astra_second_round(base, tmp_path):
    """Astra re-review: a missing command, residual outputs, timeouts of another length,
    over-broad path normalisation and repeated flags never certify a reproduction."""
    res, fz, h = copy(base, tmp_path), base['fz'], base['h']
    for cmd in (None, 'absent'):                         # a run record must carry its command
        rec = dict(h['sensitivity'])
        if cmd == 'absent':
            rec.pop('cmd')
        else:
            rec['cmd'] = None
        assert not CLI.check_sensitivity(res, fz, {**h, 'sensitivity': rec}, 'runs.csv')['reproduced']
    # a derive error matching the re-run's error, but with a residual output: not certified
    fz_bad = {'design': {**fz['design'], 'sensitivity': {**fz['design']['sensitivity'], 'K': 24}}}
    (tmp_path / 'x').mkdir()
    again = AN.run_sensitivity(fz_bad['design']['sensitivity'], res / 'runs.csv', 1, tmp_path / 'x')
    assert again['stage'] == 'derive'
    hb = {**h, 'sensitivity': again}
    assert (res / 'analysis_sensitivity.json').exists()                # residual from the fixture
    assert not CLI.check_sensitivity(res, fz_bad, hb, 'runs.csv')['reproduced']
    (res / 'analysis_sensitivity.json').unlink()
    (res / 'analysis_sensitivity_input.csv').write_bytes((tmp_path / 'x' / 'analysis_sensitivity_input.csv').read_bytes())
    assert CLI.check_sensitivity(res, fz_bad, hb, 'runs.csv')['reproduced']
    # a timeout of another length never matches
    tmo = {'cmd': h['sensitivity']['cmd'], 'stage': 'run', 'error_type': 'TimeoutExpired',
           'error': 'TimeoutExpired: x', 'timeout_s': 1, 'env': h['sensitivity']['env']}
    assert not CLI.check_sensitivity(res, fz, {**h, 'sensitivity': tmo}, 'runs.csv')['reproduced']
    # only known paths are normalised
    env = {'root': '/r', 'out': '/o', 'prefixes': ['/py']}
    assert CLI._norm('count 1/2/3', env) != CLI._norm('count 1/99/3', env)
    assert CLI._norm('/o/a.json and /r/x.py', env) == '<OUT>/a.json and <ROOT>/x.py'
    # a repeated flag (argparse takes the last) is refused
    cmd = [FROZEN_SCRIPT, *h['cmd'][1:]]
    assert CLI.primary_cmd_ok(cmd, fz, base['res'], COMMIT)
    assert not CLI.primary_cmd_ok(cmd + ['--replicates', '2'], fz, base['res'], COMMIT)
    assert not CLI.primary_cmd_ok(cmd + [str(res / 'other.csv')], fz, base['res'], COMMIT)


def test_tables_with_missing_metadata(base, tmp_path):
    res = copy(base, tmp_path)
    (res / 'truncation_report.json').unlink()                       # state unknown
    t = tables(res, tmp_path, base['fz'])
    assert 'NON-INFORMATIVE (D9)' in t and 'unknown (no truncation report)' in t
    (res / 'truncation_report.json').write_text(json.dumps({'K_scheduled': 30,
        'K_in_complete_blocks': 30, 'closed_out_runs': 0, 'analysis_flag': '', 'blocks': []}))
    assert 'unknown (no entry in the truncation report)' in tables(res, tmp_path, base['fz'])
    (res / 'analysis_hashes.json').unlink()                         # no seal at all
    assert 'No analysis_hashes.json' in tables(res, tmp_path, base['fz'])
    # no sensitivity frozen but one recorded: flagged, never printed as a result
    res2 = copy(base, tmp_path / 'b')
    assert '**Inconsistent:**' in tables(res2, tmp_path, {'design': {'S': 1}})


def test_seal_handler_never_raises(base, tmp_path, monkeypatch):
    out = tmp_path / 'o'
    out.mkdir()

    def boom(o, r):
        raise OSError('disk full')
    real = Path.unlink

    def no_unlink(self, *a, **k):
        if self.name == 'analysis_hashes.json.tmp':
            raise PermissionError('denied')
        return real(self, *a, **k)
    monkeypatch.setattr(Path, 'unlink', no_unlink)
    assert AN.seal_sensitivity(out, {}, base['fz']['design']['sensitivity'],
                               tmp_path / 'missing.csv', 1, 1, seal=boom) is False


def test_primary_command_must_match_the_freeze(base):
    res, fz = base['res'], base['fz']
    cmd = [FROZEN_SCRIPT, *base['h']['cmd'][1:]]
    assert CLI.primary_cmd_ok(cmd, fz, res, COMMIT)
    assert not CLI.primary_cmd_ok(cmd + ['--seed', '3'], fz, res, COMMIT)
    assert not CLI.primary_cmd_ok(cmd, {'design': {**fz['design'], 'S': 4}}, res, COMMIT)
    # the script must be the frozen module inside this commit's verified extraction (Astra r3)
    for script in ('/other/not_twinguard_analysis.py', base['h']['cmd'][0],
                   '/tmp/twinguard_frozen_ffffffffffff_x/twinguard/twinguard_analysis.py'):
        assert not CLI.primary_cmd_ok([script, *cmd[1:]], fz, res, COMMIT)
    assert not CLI.primary_cmd_ok(cmd, fz, res, None)


def test_second_seal_failure_keeps_the_primary_seal(base, tmp_path):
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'analysis_output.json').write_text('{}')
    record = {'cmd': [], 'rc': 0, 'sensitivity': {'pending': 'runs after the primary seal'}}
    AN.write_hashes(out, record)
    first = (out / 'analysis_hashes.json').read_text()

    def boom(o, r):
        raise OSError('disk full')
    assert AN.seal_sensitivity(out, dict(record), base['fz']['design']['sensitivity'],
                               tmp_path / 'missing.csv', 1, 0, seal=boom) is False
    assert (out / 'analysis_hashes.json').read_text() == first
    assert json.loads(first)['sensitivity'] == {'pending': 'runs after the primary seal'}


def tables(res, tmp_path, fz):
    out, f = tmp_path / 't.md', tmp_path / 'fz.json'
    f.write_text(json.dumps(fz))
    TB.main(['--results', str(res), '--freeze', str(f), '--out', str(out)])
    return out.read_text()


def test_tables_follow_the_d9_reporting_rule(base, tmp_path):
    res = copy(base, tmp_path)
    t = tables(res, tmp_path, base['fz'])
    assert 'Prespecified sensitivity (D9' in t and 'K evaluable / df' in t
    assert 'equals the sensitivity H1: yes' in t                  # D9: H1 = primary LOFO entry
    assert 'LOFO range over 10 sectors' in t and 'Agrees' in t
    assert 'NON-INFORMATIVE' not in t
    # the excluded sector's block truncated -> non-informative
    tr = json.loads((res / 'truncation_report.json').read_text())
    for b in tr['blocks']:
        if b['family'] == base['fam']:
            b['state'] = 'truncated'
    (res / 'truncation_report.json').write_text(json.dumps(tr))
    t = tables(res, tmp_path, base['fz'])
    assert 'NON-INFORMATIVE (D9)' in t and 'non-informative (truncation)' in t
    # never silent: a missing output or an unsealed record is reported as missing
    (res / 'analysis_sensitivity.json').unlink()
    assert '**Not available.**' in tables(res, tmp_path, base['fz'])
    h = json.loads((res / 'analysis_hashes.json').read_text())
    h['sensitivity'] = {'pending': 'runs after the primary seal'}
    (res / 'analysis_hashes.json').write_text(json.dumps(h))
    assert '**Not available.**' in tables(res, tmp_path, base['fz'])


def test_reproduce_astra_third_round(base, tmp_path, monkeypatch):
    """Astra r3: full error text compared; path normalisation by whole components; two
    timeouts of different length; the sensitivity must run from the primary's code root."""
    res, fz, h = copy(base, tmp_path), base['fz'], base['h']
    (res / 'analysis_sensitivity.json').unlink()
    env = h['sensitivity']['env']
    e1, e2 = {'root': '/work/repo'}, {'root': '/build/repo'}
    assert CLI._norm('x /work/repository/a', e1) != CLI._norm('x /build/repository/a', e2)
    assert CLI._norm('File "/work/repo/t.py"', e1) == CLI._norm('File "/build/repo/t.py"', e2)

    def fake(rec):           # a re-run that ends in the given error, with no files written
        def run(spec, inp, S, out, timeout=AN.SENSITIVITY_TIMEOUT_S):
            return {**rec, 'env': {**env, 'out': str(out)}}
        return run
    long_a = {'cmd': None, 'stage': 'derive', 'error_type': 'ValueError',
              'error': 'ValueError: ' + 'x' * 400 + 'A'}
    long_b = {**long_a, 'error': 'ValueError: ' + 'x' * 400 + 'B'}
    monkeypatch.setattr(AN, 'run_sensitivity', fake(long_b))
    (res / 'analysis_sensitivity_input.csv').unlink()
    pub = {**long_a, 'env': env}
    assert not CLI.check_sensitivity(res, fz, {**h, 'sensitivity': pub}, 'runs.csv')['reproduced']
    monkeypatch.setattr(AN, 'run_sensitivity', fake(long_a))
    assert CLI.check_sensitivity(res, fz, {**h, 'sensitivity': pub}, 'runs.csv')['reproduced']
    # two timeouts: only the frozen length on both sides certifies
    tmo = {'cmd': h['sensitivity']['cmd'], 'stage': 'run', 'error_type': 'TimeoutExpired',
           'error': 'TimeoutExpired: t', 'timeout_s': AN.SENSITIVITY_TIMEOUT_S}
    monkeypatch.setattr(AN, 'run_sensitivity', fake(tmo))
    ok = CLI.check_sensitivity(res, fz, {**h, 'sensitivity': {**tmo, 'env': env}}, 'runs.csv')
    assert ok['reproduced'], ok
    short = {**tmo, 'timeout_s': 1, 'env': env}
    assert not CLI.check_sensitivity(res, fz, {**h, 'sensitivity': short}, 'runs.csv')['reproduced']
    monkeypatch.setattr(AN, 'run_sensitivity', fake({**tmo, 'timeout_s': 1}))
    assert not CLI.check_sensitivity(res, fz, {**h, 'sensitivity': {**tmo, 'env': env}},
                                     'runs.csv')['reproduced']
    # the sensitivity must have run from the primary's code root
    other = {**h['sensitivity'], 'env': {**env, 'root': '/elsewhere'}}
    assert not CLI.check_sensitivity(res, fz, {**h, 'sensitivity': other}, 'runs.csv')['reproduced']


def test_tables_never_abort_on_missing_fields(base, tmp_path):
    res = copy(base, tmp_path)
    tr = json.loads((res / 'truncation_report.json').read_text())
    for b in tr['blocks']:
        if b['family'] == base['fam']:
            del b['state']
    (res / 'truncation_report.json').write_text(json.dumps(tr))
    t = tables(res, tmp_path, base['fz'])
    assert 'NON-INFORMATIVE (D9)' in t and 'no state in the truncation report' in t
    h = json.loads((res / 'analysis_hashes.json').read_text())
    del h['sensitivity']
    (res / 'analysis_hashes.json').write_text(json.dumps(h))
    assert 'The seal has no sensitivity record' in tables(res, tmp_path, base['fz'])
