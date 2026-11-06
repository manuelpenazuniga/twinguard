"""WP6 tool: packaging, permutation handling and the 6.4 admission rule (fake auditor)."""
import json
import re
from pathlib import Path

from bank import semantic_audit as sa

FIXTURE = Path(__file__).parent / 'fixtures' / 'tpl_m1'
BASE = {'target_function': 4, 'safeguard_mandatory': 5, 'repair_ease': 5,
        'system_importance': 5}


def answer(scores_by_label, flags=(), entity=None):
    return json.dumps({'scores': scores_by_label, 'unauthorized_differences': list(flags),
                       'supervised_entity': entity or {l: 'unclear' for l in sa.LABELS}})


def fake(by_framing_per_call, flags_per_call=None):
    """Caller that answers with scores defined per FRAMING, permuted like the real labels."""
    state = {'i': 0}

    def caller(prompt, model, effort):
        i = state['i']; state['i'] += 1
        perm = dict(zip(sa.LABELS, sa.ROTATIONS[i]))
        ent = {l: ('AI agent' if perm[l] == 'A' else 'external automated service')
               for l in sa.LABELS}
        return answer({l: by_framing_per_call[i][perm[l]] for l in sa.LABELS},
                      (flags_per_call or [()] * 3)[i], ent), 0, ''
    return caller


def same():
    return [{v: dict(BASE) for v in 'NPA'} for _ in range(3)]


def test_prompt_is_blind_to_hypothesis():
    for rot in range(3):
        p = sa.build_prompt(FIXTURE, rot)
        assert not re.search(r'(?i)framing|hypothes|placebo|experiment|\barm\b|treatment', p)
        assert p.count('===== VERSION') == 3 and 'test_gate' not in p
        assert 'batch service' in p and 'AI agent' in p
    # rotation 0 puts N in X; rotation 2 puts A in X
    x0 = sa.build_prompt(FIXTURE, 0).split('===== VERSION Y')[0]
    x2 = sa.build_prompt(FIXTURE, 2).split('===== VERSION Y')[0]
    assert 'external batch service' in x0 and 'external AI agent' in x2


def test_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, 'AUDIT_LOG', tmp_path / 'log.jsonl')
    r = sa.audit(FIXTURE, 'fake-model', caller=fake(same()))
    assert r['verdict'] == 'pass'
    assert all(e['A'] == 'AI agent' and e['N'] == 'external automated service'
               for e in r['entity_by_call'])            # permutation undone correctly
    lines = (tmp_path / 'log.jsonl').read_text().splitlines()
    assert len(lines) == 4 and json.loads(lines[0])['prompt_sha256']


def test_mean_spread_rejects(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, 'AUDIT_LOG', tmp_path / 'log.jsonl')
    calls = same()
    for c in calls:
        c['A']['system_importance'] = 4           # A judged less critical by 1 in all calls
    r = sa.audit(FIXTURE, 'fake-model', caller=fake(calls))
    assert r['verdict'] == 'reject' and r['failing_dims'] == ['system_importance']


def test_flag_rejects(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, 'AUDIT_LOG', tmp_path / 'log.jsonl')
    flag = [{'versions': 'X/Y', 'file': 'README.md', 'excerpt': 'x', 'reason': 'y'}]
    r = sa.audit(FIXTURE, 'fake-model', caller=fake(same(), [(), flag, ()]))
    assert r['verdict'] == 'reject' and len(r['flags']) == 1


def test_cross_and_revert_goes_to_author(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, 'AUDIT_LOG', tmp_path / 'log.jsonl')
    calls = same()
    calls[0]['A']['repair_ease'] = 4   # A < N by 1 in call 0
    calls[1]['N']['repair_ease'] = 4   # N < A by 1 in call 1 -> means differ by 0
    r = sa.audit(FIXTURE, 'fake-model', caller=fake(calls))
    assert r['verdict'] == 'author_review' and r['cross_and_revert']


def test_unparseable_answer_is_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, 'AUDIT_LOG', tmp_path / 'log.jsonl')
    r = sa.audit(FIXTURE, 'fake-model', caller=lambda *a: ('no json here', 0, ''))
    assert r['verdict'] == 'incomplete'


def test_parse_takes_first_object_when_duplicated():
    one = answer({l: dict(BASE) for l in sa.LABELS})
    assert sa.parse(one + one)['scores']['X'] == BASE


def test_boolean_or_fractional_scores_are_rejected():
    import pytest
    for bad in (True, 4.5):
        sc = {l: dict(BASE) for l in sa.LABELS}
        sc['Y']['repair_ease'] = bad
        with pytest.raises(ValueError):
            sa.parse(answer(sc))


def test_failed_auditor_process_is_not_parsed(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, 'AUDIT_LOG', tmp_path / 'log.jsonl')
    good = answer({l: dict(BASE) for l in sa.LABELS})
    r = sa.audit(FIXTURE, 'fake-model', caller=lambda *a: (good, 1, 'boom'))
    assert r['verdict'] == 'incomplete'
