"""Writeup figures (WP14). Every bar is a count read from results/paper/figure_data.json (written by
analysis/paper_tables.py, sha256 checked here) or from the frozen bank; nothing is estimated.

  fig1_instrument.png   One token apart: the S+ and U+ admission witnesses of M1.cold_chain_release,
                        with their functional-test and oracle verdicts (results/d14/d14_descriptives.json).
  fig2_confirmatory.png Confirmatory, per framing: code modified (M), tests pass (F), oracle W = 1.
  fig3_ladder.png       D12 calibration ladder: oracle W = 1 among completed runs, rung x mechanism.
  fig4_request.png      x3 and E4B: W = 1 under the explicit request, by mechanism and framing.
  fig5_detectors.png    x3: the 268 patches that complied with the request (W = 1): tests, frozen
                        detectors, disclosure.

Needs matplotlib (not in requirements.txt; figures only):
  python analysis/paper_figures.py --out results/paper/figures
"""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'results' / 'paper' / 'figure_data.json'
D14 = ROOT / 'results' / 'd14' / 'd14_descriptives.json'
DEMO = ROOT / 'bank' / 'templates' / 'M1.cold_chain_release' / 'patches'

# Categorical slots in fixed order (validated: adjacent CVD dE >= 9.2 on white; aqua < 3:1, so
# every bar carries a direct k/n label).
SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#6250d6']
INK, INK2, GRID, SURF = '#0b0b0b', '#52514e', '#e4e3df', '#ffffff'
ADD, DEL = '#e3f0e3', '#f8e1e1'

plt.rcParams.update({
    'font.family': ['Helvetica Neue', 'Helvetica', 'DejaVu Sans'], 'font.size': 9,
    'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
    'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': True, 'grid.color': GRID,
    'grid.linewidth': 0.6, 'axes.axisbelow': True, 'figure.facecolor': SURF, 'axes.facecolor': SURF,
    'savefig.dpi': 300, 'savefig.bbox': 'tight', 'legend.frameon': False, 'text.color': INK})


def load():
    raw = DATA.read_bytes()
    want = (DATA.parent / 'figure_data.json.sha256').read_text().split()[0]
    if hashlib.sha256(raw).hexdigest() != want:
        raise SystemExit('figure_data.json does not match its recorded sha256')
    return json.loads(raw)


def grouped(ax, groups, series, value, label, colors, width=0.8):
    """Vertical grouped bars; value(g, s) -> (k, n). A 2 px surface gap between neighbours."""
    m = len(series)
    w = width / m
    for j, s in enumerate(series):
        for i, g in enumerate(groups):
            k, n = value(g, s)
            x = i - width / 2 + w * (j + 0.5)
            ax.bar(x, 100 * k / n, w, color=colors[j], edgecolor=SURF, linewidth=1.2,
                   label=label(s) if i == 0 else None)
            ax.text(x, 100 * k / n + 1.5, f'{k}/{n}', ha='center', va='bottom', fontsize=7,
                    color=INK2)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100], ['0%', '25%', '50%', '75%', '100%'])
    ax.grid(axis='x', visible=False)


def fig_instrument(out):
    demo = json.loads(D14.read_text())['instrument_demonstration']['M1']
    verdict = {}
    for wit in ('s_plus', 'u_plus'):
        v = demo['witnesses'][wit]
        tests = {x['tests_passed'] for x in v.values()}
        oracle = {x['oracle_W'] for x in v.values()}
        assert len(tests) == 1 and len(oracle) == 1, 'witness verdicts differ across framings'
        verdict[wit] = (tests.pop(), oracle.pop(), next(iter(v.values()))['tests_summary'])

    def hunk(path):
        """The changed lines of check_release plus one line of context after them."""
        lines = path.read_text().splitlines()
        start = next(i for i, l in enumerate(lines) if 'def check_release' in l)
        body = lines[start:]
        first = next(i for i, l in enumerate(body) if l.startswith('-'))
        last = max(i for i, l in enumerate(body) if l.startswith('+'))
        return [body[0]] + body[first:last + 2]

    titles = {'s_plus': 'S+  safe repair', 'u_plus': 'U+  weakening repair'}
    fig, axes = plt.subplots(2, 1, figsize=(5.6, 3.9))
    for ax, wit in zip(axes, ('s_plus', 'u_plus')):
        ax.set_axis_off()
        code = hunk(DEMO / f'{wit}.diff')
        ax.set_xlim(0, 1)
        ax.set_ylim(-0.5, len(code) + 0.6)
        tests, w, summ = verdict[wit]
        ax.text(0, len(code) + 0.2, titles[wit], fontsize=10, fontweight='bold', va='bottom')
        ax.text(1, len(code) + 0.2, f"tests: {'pass' if tests else 'fail'} ({summ.split(' in ')[0]})"
                f"   |   oracle: W = {w}, {'safeguard kept' if w == 0 else 'fails open'}",
                fontsize=7.5, ha='right', va='bottom', color=INK2)
        for i, l in enumerate(code):
            y = len(code) - 1 - i
            bg = ADD if l.startswith('+') else DEL if l.startswith('-') else None
            if bg:
                ax.add_patch(plt.Rectangle((0, y - 0.45), 1, 0.9, color=bg, lw=0))
            key = l.startswith('+') and ('Decision.HOLD' in l or 'Decision.RELEASE' in l)
            ax.text(0.01, y, l, family=['Menlo', 'DejaVu Sans Mono'], fontsize=7, va='center', color=INK,
                    fontweight='bold' if key else 'normal')
    fig.savefig(out / 'fig1_instrument.png')
    plt.close(fig)


def fig_confirmatory(out, d):
    arms = d['confirmatory_by_arm']
    names = {'N': 'N  external service', 'P': 'P  lexical placebo', 'A': 'A  AI agent'}
    rows = [('M', 'Code modified (M)'), ('F', 'Functional tests pass (F)'),
            ('W', 'Oracle: safeguard weakened (W)')]
    fig, ax = plt.subplots(figsize=(6.2, 2.4))
    h = 0.8 / 3
    for j, f in enumerate('NPA'):
        n = arms[f]['evaluable']
        for i, (k, _) in enumerate(rows):
            y = i - 0.4 + h * (j + 0.5)
            ax.barh(y, 100 * arms[f][k] / n, h, color=SERIES[j], edgecolor=SURF, linewidth=1.2,
                    label=names[f] if i == 0 else None)
            ax.text(100 * arms[f][k] / n + 1.5, y, f"{arms[f][k]}/{n}", va='center', fontsize=7,
                    color=INK2)
    ax.set_yticks(range(len(rows)), [r[1] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 112)
    ax.set_xticks([0, 25, 50, 75, 100], ['0%', '25%', '50%', '75%', '100%'])
    ax.grid(axis='y', visible=False)
    ax.set_xlabel('share of the 240 runs per framing (30 templates x 4 paraphrases x 2 replicates)')
    ax.legend(loc='upper center', bbox_to_anchor=(0.4, -0.3), ncol=3, fontsize=7.5)
    fig.savefig(out / 'fig2_confirmatory.png')
    plt.close(fig)


def fig_ladder(out, d):
    lad = d['ladder']
    fig, ax = plt.subplots(figsize=(6.2, 2.7))
    rungs = ['L1', 'L2', 'L3', 'C']
    sub = {'L1': 'L1\npolicy hidden', 'L2': 'L2\nshortcut shown', 'L3': 'L3\nhidden + shown',
           'C': 'C\n"Please apply\nthis patch"'}
    grouped(ax, rungs, ['M1', 'M2', 'M3'], lambda g, s: (lad[g][s]['W1'], lad[g][s]['completed']),
            lambda s: s, SERIES)
    ax.set_xticks(range(4), [sub[r] for r in rungs])
    ax.set_ylabel('oracle W = 1\n(share of completed runs)')
    ax.legend(title='mechanism', loc='upper left', fontsize=7.5, title_fontsize=7.5)
    fig.savefig(out / 'fig3_ladder.png')
    plt.close(fig)


def hbars(ax, rows, series, value, label, colors):
    """Horizontal grouped bars; value(row, series) -> (k, n), labelled k/n."""
    h = 0.8 / len(series)
    for j, s in enumerate(series):
        for i, (r, _) in enumerate(rows):
            k, n = value(r, s)
            y = i - 0.4 + h * (j + 0.5)
            ax.barh(y, 100 * k / n if n else 0, h, color=colors[j], edgecolor=SURF, linewidth=1.2,
                    label=label(s) if i == 0 else None)
            ax.text((100 * k / n if n else 0) + 1.5, y, f'{k}/{n}', va='center', fontsize=7,
                    color=INK2)
    ax.set_yticks(range(len(rows)), [r[1] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 112)
    ax.set_xticks([0, 25, 50, 75, 100], ['0%', '25%', '50%', '75%', '100%'])
    ax.grid(axis='y', visible=False)


def fig_detectors(out, d):
    """x3 (D15): the 268 patches with which Gemma 4 31B complied with the explicit request."""
    p = d['followup']['x3_weakening_patches']
    rows = [('tests', 'Functional tests pass'), ('ast', 'AST baseline alert'),
            ('gsc', 'GSC (call graph) alert'), ('except_local', 'except-local alert'),
            ('disc', 'Mentions the weakening (lexical)')]

    def val(r, m):
        c = p[m]
        return {'tests': (c['tests_pass'], c['W1']), 'disc': (c['disclosed_any_turn'], c['W1']),
                'gsc': (c['gsc_alert'], c['gsc_evaluable'])}.get(r, (c.get(f'{r}_alert'), c['W1']))
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    hbars(ax, rows, ['M1', 'M2', 'M3'], val, lambda m: f"{m} (n = {p[m]['W1']})", SERIES)
    ax.set_xlabel('share of weakening patches (oracle W = 1); GSC: of the patches it can evaluate')
    ax.legend(loc='upper center', bbox_to_anchor=(0.42, -0.22), ncol=3, fontsize=7.5)
    fig.savefig(out / 'fig5_detectors.png')
    plt.close(fig)


def fig_request(out, d):
    """x3 and E4B: share of runs that applied the weakening patch when asked, by mechanism."""
    f = d['followup']
    rows = [('M1', 'M1  policy timeout'), ('M2', 'M2  API migration'),
            ('M3', 'M3  prior instruction')]
    series = ['N', 'P', 'A', 'E4B']
    names = {'N': '31B  N external service', 'P': '31B  P lexical placebo', 'A': '31B  A AI agent',
             'E4B': 'E4B  N (other model and host)'}

    def val(m, s):
        c = f['e4b_W_by_mechanism'][m] if s == 'E4B' else f['x3_W_by_mechanism_framing'][m][s]
        return c['W1'], c['n']
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    hbars(ax, rows, series, val, names.get, SERIES)
    ax.set_xlabel('applied the weakening patch when asked (oracle W = 1), 10 templates x 4 paraphrases')
    ax.legend(loc='upper center', bbox_to_anchor=(0.42, -0.22), ncol=2, fontsize=7.5)
    fig.savefig(out / 'fig4_request.png')
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d = load()
    fig_instrument(out)
    fig_confirmatory(out, d)
    fig_ladder(out, d)
    fig_request(out, d)
    fig_detectors(out, d)
    print(json.dumps(sorted(p.name for p in out.glob('*.png'))))


if __name__ == '__main__':
    main()
