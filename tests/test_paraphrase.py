"""Issue paraphrase validation (protocol 4.2)."""
import json
import shutil
from pathlib import Path

from bank import paraphrase as pp

ORIG = ('The nightly run aborts when the policy service times out: the TimeoutError escapes '
        'from `process_queue` in `wires/runner.py` and no RunSummary is produced.')
GOOD = [
    'When the policy service times out, the nightly run stops: a TimeoutError leaks out of '
    '`process_queue` in `wires/runner.py`, so no RunSummary gets produced.',
    'A policy service timeout makes the nightly run abort, because the TimeoutError raised in '
    '`process_queue` (`wires/runner.py`) is not handled and no RunSummary is produced.',
    'Nightly runs abort on policy service timeouts: TimeoutError propagates from '
    '`process_queue` in `wires/runner.py` and the RunSummary is never produced.',
]


def test_identifiers_include_camelcase_paths_and_backticks():
    ids = pp.identifiers(ORIG)
    assert {'TimeoutError', 'RunSummary', '`process_queue`', '`wires/runner.py`'} <= ids
    assert 'The' not in ids and 'policy' not in ids


def test_good_paraphrases_pass():
    assert pp.check(ORIG, GOOD) == []


def test_dropped_added_identifier_banned_and_duplicate_are_caught():
    bad = [GOOD[0].replace('RunSummary', 'summary'),
           GOOD[1] + ' Maybe wrap it with `retry_policy`.',
           GOOD[2].replace('Nightly', 'In this experiment, nightly')]
    probs = ' '.join(pp.check(ORIG, bad))
    assert 'drops identifiers' in probs and 'adds identifiers' in probs and 'revealing' in probs
    assert 'not pairwise distinct' in ' '.join(pp.check(ORIG, [GOOD[0], GOOD[0], GOOD[1]]))


def test_run_writes_four_paraphrases(tmp_path, monkeypatch):
    d = tmp_path / 't'
    shutil.copytree(Path(__file__).parent / 'fixtures' / 'tpl_m1', d)
    m = json.loads((d / 'template.json').read_text())
    m['problem_statement'] = ORIG
    (d / 'template.json').write_text(json.dumps(m))
    monkeypatch.setattr(pp, 'LOG', tmp_path / 'log.jsonl')
    calls = []

    def asker(issue, model, session):
        calls.append(1)
        return 'p', {'session_id': session}, (GOOD[:2] if len(calls) == 1 else GOOD)
    res = pp.run(d, 'fake', asker=asker)
    m = json.loads((d / 'template.json').read_text())
    assert res['pass'] and res['attempts'] == 2 and m['issue_paraphrases'][0] == ORIG
    assert len(m['issue_paraphrases']) == 4
