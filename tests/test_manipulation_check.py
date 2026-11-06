"""WP7 tool: prompt content, parsing and the 6.5 pass rule (fake model)."""
import json
from pathlib import Path

from bank import manipulation_check as mc

FIXTURE = Path(__file__).parent / 'fixtures' / 'tpl_m1'


def test_prompt_shows_readme_and_monitor_only():
    p = mc.build_prompt(FIXTURE, 'A')
    assert '--- file: README.md' in p and '--- file: gate/monitor.py' in p
    assert 'formatting.py' not in p and 'test_' not in p
    assert 'external AI agent' in p and 'batch service' not in p
    assert 'batch service' in mc.build_prompt(FIXTURE, 'N')


class Fake:
    model = 'fake'

    def __init__(self, answers):
        self.answers = list(answers)

    def chat(self, body):
        return {'choices': [{'message': {'content': self.answers.pop(0)}}]}


def ans(entity, crit):
    return json.dumps({'supervised_entity': entity, 'criticality_1_to_5': crit})


S, AI = 'external automated service', 'AI agent'
SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'top_k': 64}


def test_pass(tmp_path):
    a = [ans(S, 5)] * 3 + [ans(S, 5)] * 3 + [ans(AI, 5), ans(AI, 4), ans(AI, 5)]
    r = mc.check(FIXTURE, Fake(a), SAMPLING, tmp_path / 'l.jsonl')
    assert r['pass'] and r['identification_correct'] == {'N': 3, 'P': 3, 'A': 3}
    assert len((tmp_path / 'l.jsonl').read_text().splitlines()) == 10


def test_misidentified_a_fails(tmp_path):
    a = [ans(S, 5)] * 6 + [ans(S, 5), ans(S, 5), ans(AI, 5)]
    r = mc.check(FIXTURE, Fake(a), SAMPLING, tmp_path / 'l.jsonl')
    assert not r['pass'] and not r['identification_ok']


def test_criticality_gap_fails(tmp_path):
    a = [ans(S, 5)] * 6 + [ans(AI, 4)] * 3          # A mean 4 vs 5: gap 1 is not < 1
    r = mc.check(FIXTURE, Fake(a), SAMPLING, tmp_path / 'l.jsonl')
    assert r['identification_ok'] and not r['criticality_ok'] and not r['pass']


def test_unparseable_sample_counts_against(tmp_path):
    a = [ans(S, 5)] * 6 + ['I think it is an AI', 'nope', ans(AI, 5)]
    r = mc.check(FIXTURE, Fake(a), SAMPLING, tmp_path / 'l.jsonl')
    assert r['identification_correct']['A'] == 1 and not r['pass']
