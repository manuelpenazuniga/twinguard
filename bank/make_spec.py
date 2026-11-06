"""Build bank/spec_matrix.csv from bank/sectors.toml (WP3; protocol 6.1 and 6.3).

Deterministic given the TOML and the seed. Rules:
  * 30 confirmatory rows: 10 sectors x one subdomain per mechanism (M1, M2, M3).
  * 6 pilot rows: 2 per mechanism, subdomains distinct from everything else.
  * Style by Latin square over sector x mechanism: the sectors are shuffled with the
    seed and style = STYLES[(sector_rank + mechanism_index) % 3]. Pilot rows get
    styles cycled within mechanism so each pilot mechanism sees two styles.
  * Neutral identifier names rotate between templates (never between framings).
  * creation_order: a seeded random permutation of 1..36, fixed before any run.
    Within a mechanism it decides which admitted templates enter if more than 10
    are admitted (protocol 6.1).

Usage: python bank/make_spec.py [--seed 20261106] [--out bank/spec_matrix.csv]
Writes the CSV and <out>.sha256 (sha256 of the CSV bytes plus the TOML hash).
"""
import argparse
import csv
import hashlib
import io
import random
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MECHANISMS = ('M1', 'M2', 'M3')
STYLES = ('functional', 'object_oriented', 'event_callbacks')
COLUMNS = ['template_id', 'split', 'family', 'mechanism', 'subdomain', 'style',
           'actor_identifier', 'monitor_identifier', 'creation_order', 'scenario_seed']
DEFAULT_SEED = 20261106


class SpecError(ValueError):
    pass


def load_sectors(path):
    data = tomllib.loads(Path(path).read_text(encoding='utf-8'))
    sectors = data['sector']
    ids = data['identifiers']
    if len(sectors) != 10:
        raise SpecError(f'expected 10 sectors, got {len(sectors)}')
    missing = [m for m in MECHANISMS if not data.get('mechanisms', {}).get(m, {}).get('contract')]
    if missing:
        raise SpecError(f'missing mechanism contract for {missing}')
    return sectors, ids


def build_rows(sectors, identifiers, seed=DEFAULT_SEED):
    rng = random.Random(seed)
    order = list(range(len(sectors)))
    rng.shuffle(order)                       # sector rank for the Latin square
    rank = {sectors[i]['name']: r for r, i in enumerate(order)}

    rows = []
    for s in sectors:
        for m_idx, m in enumerate(MECHANISMS):
            cell = s[m]
            rows.append(dict(split='confirmatory', family=s['name'], mechanism=m,
                             subdomain=cell['subdomain'], scenario_seed=cell['seed'],
                             style=STYLES[(rank[s['name']] + m_idx) % 3]))
    pilots = sorted(((p['mechanism'], p['subdomain'], s['name'], p['seed'])
                     for s in sectors for p in s.get('pilot', [])))
    for i, (m, sub, fam, sd) in enumerate(pilots):
        rows.append(dict(split='pilot', family=fam, mechanism=m, subdomain=sub,
                         scenario_seed=sd, style=STYLES[i % 3]))

    # identifiers: independent seeded rotations, each name used about equally
    n = len(rows)
    actors = (identifiers['actor'] * (n // len(identifiers['actor']) + 1))[:n]
    monitors = (identifiers['monitor'] * (n // len(identifiers['monitor']) + 1))[:n]
    rng.shuffle(actors)
    rng.shuffle(monitors)
    creation = list(range(1, n + 1))
    rng.shuffle(creation)
    for row, a, mo, c in zip(rows, actors, monitors, creation):
        row.update(actor_identifier=a, monitor_identifier=mo, creation_order=c,
                   template_id=f"{row['mechanism']}.{row['subdomain']}")
    validate(rows)
    return rows


def validate(rows):
    conf = [r for r in rows if r['split'] == 'confirmatory']
    pilot = [r for r in rows if r['split'] == 'pilot']
    if len(conf) != 30 or len(pilot) != 6:
        raise SpecError(f'need 30 confirmatory + 6 pilot rows, got {len(conf)} + {len(pilot)}')
    subs = [r['subdomain'] for r in rows]
    if len(set(subs)) != len(subs):
        raise SpecError('a subdomain is repeated')
    for m in MECHANISMS:
        if sum(r['mechanism'] == m for r in conf) != 10:
            raise SpecError(f'{m} does not have 10 confirmatory rows')
        if sum(r['mechanism'] == m for r in pilot) != 2:
            raise SpecError(f'{m} does not have 2 pilot rows')
    fams = {}
    for r in conf:
        fams.setdefault(r['family'], []).append(r['mechanism'])
    if len(fams) != 10 or any(sorted(v) != list(MECHANISMS) for v in fams.values()):
        raise SpecError('each sector must hold exactly one confirmatory row per mechanism')
    for f, ms in fams.items():
        styles = {r['style'] for r in conf if r['family'] == f}
        if len(styles) != 3:
            raise SpecError(f'Latin square violated in sector {f}')
    if sorted(r['creation_order'] for r in rows) != list(range(1, len(rows) + 1)):
        raise SpecError('creation_order is not a permutation')


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator='\n')
    w.writeheader()
    for r in sorted(rows, key=lambda r: r['creation_order']):
        w.writerow({k: r[k] for k in COLUMNS})
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--sectors', default=str(HERE / 'sectors.toml'))
    ap.add_argument('--seed', type=int, default=DEFAULT_SEED)
    ap.add_argument('--out', default=str(HERE / 'spec_matrix.csv'))
    a = ap.parse_args(argv)
    sectors, ids = load_sectors(a.sectors)
    text = to_csv(build_rows(sectors, ids, a.seed))
    out = Path(a.out)
    out.write_text(text, encoding='utf-8')
    toml_hash = hashlib.sha256(Path(a.sectors).read_bytes()).hexdigest()
    csv_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    gen_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    Path(str(out) + '.sha256').write_text(
        f'{csv_hash}  {out.name}\n{toml_hash}  {Path(a.sectors).name}\n{gen_hash}  make_spec.py\n'
        f'seed {a.seed}\npython {sys.version.split()[0]}\n', encoding='utf-8')
    print(f'{out}: {csv_hash}', file=sys.stderr)


if __name__ == '__main__':
    main()
