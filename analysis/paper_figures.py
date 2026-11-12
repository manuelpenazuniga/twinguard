"""Writeup figures (WP14). Every mark is a count read from results/paper/figure_data.json (written by
analysis/paper_tables.py, sha256 checked here) or from committed files of the frozen bank; nothing
is estimated here. The one interval drawn (Fig. 3b) is the sealed x3 estimate, copied, not computed.

Body
  fig1_instrument     Two reference repairs of M1.cold_chain_release (template witnesses, not agent
                      output) one token apart, with their test, oracle and frozen-detector verdicts
                      (results/d14/d14_descriptives.json, results/witnesses/witness_detectors.jsonl).
  fig2_confirmatory   a: confirmatory M/F/W per framing; b: D12 calibration, W among completed runs
                      per rung (framings pooled).
  fig3_request        x3 (31B): a: W under the explicit request by mechanism x framing;
                      b: the sealed A - N estimate with its 90% and 95% CIs against the SESOI.
  fig4_detectors      x3: a: the 268 weakening patches against tests, frozen detectors and the
                      lexical disclosure pattern, by mechanism; b: what each frozen gate policy holds
                      back among weakening patches and safe repairs (GSC alarms vs abstentions).
Appendix
  figA1_models        D16/D17/D17b next to x3 N: per Gemma 4 configuration, weakened / safe repair /
                      not weakened with failing tests (120 runs each; descriptive, no intervals).

Style: Tinos (the Times-metric serif of the paper body) and Source Code Pro for code (SIL OFL,
bundled in analysis/fonts so the figures render the same on any machine); framings in Paul Tol's high-contrast scheme plus marker shape; every other
category in greys and hatching; 6.75 in wide; PNG (300 dpi) and PDF with embedded fonts.

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
from matplotlib import font_manager  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'results' / 'paper' / 'figure_data.json'
D14 = ROOT / 'results' / 'd14' / 'd14_descriptives.json'
WITNESS_DET = ROOT / 'results' / 'witnesses' / 'witness_detectors.jsonl'
DEMO_ID = 'M1.cold_chain_release'
DEMO = ROOT / 'bank' / 'templates' / DEMO_ID / 'patches'
FONTS = Path(__file__).resolve().parent / 'fonts'

# Framings: Paul Tol's high-contrast scheme (blue / ochre / wine; distinct in greyscale and under
# CVD, checked with the dataviz validator: CVD dE >= 16, normal-vision dE >= 24) plus marker shape.
# Ochre is below 3:1 on white, so every marker has a dark edge and every value a printed count.
FRAMING = {'N': ('N  external service', '#004488', 'o'),
           'P': ('P  lexical placebo', '#DDAA33', 's'),
           'A': ('A  AI agent', '#BB5566', '^')}
INK, INK2, MUTED, RULE, BAND = '#1a1a1a', '#4d4d4d', '#8c8c8c', '#d4d4d4', '#ececec'
DARK, MID, LIGHT = '#3b3b3b', '#9a9a9a', '#ffffff'      # non-framing categories: greys + hatch
WIDTH = 6.75
MINUS = '−'


def setup():
    for f in sorted(FONTS.glob('*.ttf')):
        font_manager.fontManager.addfont(str(f))
    plt.rcParams.update({
        'font.family': 'serif', 'font.serif': ['Tinos', 'DejaVu Serif'],
        'font.monospace': ['Source Code Pro', 'DejaVu Sans Mono'],
        'mathtext.fontset': 'custom', 'mathtext.it': 'Tinos:italic',
        'mathtext.rm': 'Tinos', 'mathtext.bf': 'Tinos:bold',
        'mathtext.cal': 'Tinos', 'mathtext.sf': 'Tinos',
        'mathtext.tt': 'Source Code Pro', 'mathtext.bfit': 'Tinos:bold:italic',
        'font.size': 8.5, 'axes.titlesize': 9, 'axes.labelsize': 8.5, 'xtick.labelsize': 8,
        'ytick.labelsize': 8.5, 'legend.fontsize': 8, 'axes.linewidth': 0.6, 'axes.edgecolor': INK2,
        'xtick.major.width': 0.6, 'ytick.major.width': 0, 'xtick.major.size': 2.5,
        'xtick.color': INK2, 'ytick.color': INK, 'axes.labelcolor': INK2, 'text.color': INK,
        'axes.spines.top': False, 'axes.spines.right': False, 'axes.spines.left': False,
        'axes.grid': False, 'legend.frameon': False, 'hatch.linewidth': 0.5,
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.03, 'figure.facecolor': 'white', 'axes.facecolor': 'white'})


def load():
    raw = DATA.read_bytes()
    want = (DATA.parent / 'figure_data.json.sha256').read_text().split()[0]
    if hashlib.sha256(raw).hexdigest() != want:
        raise SystemExit('figure_data.json does not match its recorded sha256')
    return json.loads(raw)


def save(fig, out, name):
    fig.savefig(out / f'{name}.png', metadata={'Software': None})
    fig.savefig(out / f'{name}.pdf', metadata={'CreationDate': None, 'Creator': None,
                                                'Producer': None})
    plt.close(fig)


def mn(v, fmt='+.1f'):
    return format(v, fmt).replace('-', MINUS)


LEFT = -5     # dot plots: room left of 0 so a zero-valued marker is drawn whole, not cut by the axes


def pct_axis(ax, right, label=None, ticks=(0, 25, 50, 75, 100), left=LEFT):
    """0-100 % axis; the spine stops at 100 so the count column to its right reads as a table.
    The 0 % gridline sits behind the markers (set_axisbelow)."""
    ax.set_xlim(left, right)
    ax.spines['bottom'].set_bounds(0, 100)
    ax.set_xticks(list(ticks), [str(t) for t in ticks[:-1]] + [f'{ticks[-1]}%'])
    ax.grid(axis='x', color=BAND, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    if label:
        ax.set_xlabel(label, x=frac(ax, 50))


def frac(ax, v):
    """Axes fraction of the data x-value v."""
    lo, hi = ax.get_xlim()
    return (v - lo) / (hi - lo)


def title(ax, letter, text):
    ax.set_title(f'{letter}   {text}', loc='left', fontweight='bold', pad=7)


def dots(ax, y, values, styles, dodge=0.24, size=30):
    """One row of a dodged dot plot. values: [(k, n)]; styles: [(colour, marker, edge)]."""
    m = len(values)
    for j, ((k, n), (c, mk, ec)) in enumerate(zip(values, styles)):
        yy = y + (j - (m - 1) / 2) * dodge
        x = 100 * k / n
        ax.plot([0, x], [yy, yy], color=c if c != LIGHT else MUTED, lw=0.7, alpha=0.45, zorder=1,
                solid_capstyle='butt')
        ax.scatter(x, yy, s=size * (1.2 if mk in '^D' else 1), marker=mk, color=c, edgecolor=ec,
                   linewidth=0.6, zorder=3 + j, clip_on=False)


def counts(ax, y, values, xs, bold=False):
    for (k, _), x in zip(values, xs):
        ax.text(x, y, f'{k}', ha='center', va='center', fontsize=8,
                fontweight='bold' if bold else 'normal')
    ax.text(xs[-1] + (xs[1] - xs[0]) * 0.55, y, f'/{values[-1][1]}', ha='left', va='center',
            fontsize=8, color=MUTED)


def headers(ax, y, xs, styles, labels, sub=None, dy=0.42, mdx=2.6):
    """Count-column headers: the series marker, its label and, optionally, a muted n below.
    Single-letter labels sit just right of the marker; longer ones are centred on the column
    with the marker mdx to the left."""
    for i, (x, (c, mk, ec), lab) in enumerate(zip(xs, styles, labels)):
        ax.scatter(x - mdx, y, s=16 * (1.2 if mk in '^D' else 1), marker=mk, color=c,
                   edgecolor=ec, linewidth=0.5, clip_on=False)
        if len(lab) == 1:
            ax.text(x + 0.4, y, lab, ha='left', va='center', fontsize=7.5, color=INK2)
        else:
            ax.text(x, y, lab, ha='center', va='center', fontsize=7.5, color=INK2)
        if sub:
            ax.text(x, y + dy, sub[i], ha='center', va='center', fontsize=7, color=MUTED)


def framing_styles(order='NPA'):
    return [(FRAMING[f][1], FRAMING[f][2], INK) for f in order]


def framing_legend(ax, x, y, ncol=3):
    ax.legend(handles=[Line2D([], [], ls='', marker=mk, color=c, markeredgecolor=INK,
                              markeredgewidth=0.5, ms=5.5, label=lab)
                       for lab, c, mk in FRAMING.values()],
              loc='upper center', bbox_to_anchor=(x, y), ncol=ncol, handletextpad=0.3,
              columnspacing=1.6)


# ---------------------------------------------------------------- Fig. 1
def fig_instrument(out):
    demo = json.loads(D14.read_text())['instrument_demonstration']['M1']
    assert demo['template_id'] == DEMO_ID
    verdict = {}
    for wit in ('s_plus', 'u_plus'):
        v = demo['witnesses'][wit]
        tests = {(x['tests_passed'], x['tests_summary'].split(' in ')[0]) for x in v.values()}
        oracle = {x['oracle_W'] for x in v.values()}
        assert len(tests) == 1 and len(oracle) == 1, 'witness verdicts differ across framings'
        verdict[wit] = (*tests.pop(), oracle.pop())
    det = {}
    for line in WITNESS_DET.read_text().splitlines():
        r = json.loads(line)
        if r['template_id'] == DEMO_ID and r['patch'] in verdict:
            det[r['patch']] = [r['states'][k] for k in ('ast', 'gsc', 'except_local')]
    assert set(det) == set(verdict)

    def body(wit):
        """check_release after the patch: context and added lines, docstring dropped."""
        lines = (DEMO / f'{wit}.diff').read_text().splitlines()
        start = next(i for i, l in enumerate(lines) if 'def check_release' in l)
        seg = lines[start:]
        last = max(i for i, l in enumerate(seg) if l.startswith('+'))
        keep = [l[1:] for l in seg[:last + 2] if not l.startswith('-')]
        return [l for l in keep if '"""' not in l]
    s, u = body('s_plus'), body('u_plus')
    assert len(s) == len(u)
    diff = [i for i, (a, b) in enumerate(zip(s, u)) if a != b]
    assert len(diff) == 1, 'the two witnesses must differ in exactly one line'
    i0 = diff[0]
    rows = ([(None, l) for l in s[:i0]] + [('s_plus', s[i0]), ('u_plus', u[i0])]
            + [(None, l) for l in s[i0 + 1:]])

    fig, ax = plt.subplots(figsize=(WIDTH, 0.235 * len(rows) + 0.75))
    ax.set_axis_off()
    n = len(rows)
    ax.set_xlim(0, 1)
    ax.set_ylim(n - 0.35, -2.1)
    X_CODE, X_T, X_O, X_D = 0.045, 0.615, 0.765, 0.925
    ax.text(0, -1.75, f'{DEMO_ID}: two reference repairs (template witnesses, not agent output)',
            fontsize=8.5, fontweight='bold', va='center')
    hy = -0.85
    for x, lab in ((X_T, 'visible tests'), (X_O, 'oracle'), (X_D, 'frozen detectors')):
        ax.text(x, hy, lab, ha='center', va='center', fontsize=7.5, color=INK2)
    ax.plot([0, 1], [hy + 0.42] * 2, color=RULE, lw=0.6)
    names = {'s_plus': 'S+', 'u_plus': 'U+'}
    for y, (wit, line) in enumerate(rows):
        if wit:
            ax.add_patch(Rectangle((0, y - 0.45), 1, 0.9, color=BAND, lw=0, zorder=0))
            ax.text(0.008, y, names[wit], fontsize=8, fontweight='bold', va='center')
            key = line.rstrip().split()[-1]
            pre = line[:line.rindex(key)]
            t = ax.text(X_CODE, y, pre.rstrip(), family='monospace', fontsize=7.6, va='center')
            gap = len(pre) - len(pre.rstrip())          # monospace advance: 0.6 em per char
            ax.annotate(key, xy=(1, 0.5), xycoords=t, xytext=(0.6 * 7.6 * gap, 0),
                        textcoords='offset points', family='monospace', fontsize=7.6,
                        va='center', ha='left', fontweight='semibold')
            passed, summ, w = verdict[wit]
            ax.text(X_T, y, summ if passed else 'fail', ha='center', va='center', fontsize=8)
            ax.text(X_O, y, f"$W$ = {w}   " + ('kept' if w == 0 else 'fails open'), ha='center',
                    va='center', fontsize=8, fontweight='normal' if w == 0 else 'bold')
            alerts = sum(st != 'no_alert' for st in det[wit])
            ax.text(X_D, y, 'no alert (0 of 3)' if alerts == 0 else f'{alerts} of 3 alert',
                    ha='center', va='center', fontsize=8)
        else:
            ax.text(X_CODE, y, line, family='monospace', fontsize=7.6, va='center', color=INK2)
    save(fig, out, 'fig1_instrument')


# ---------------------------------------------------------------- Fig. 2
def fig_confirmatory(out, d):
    arms = d['confirmatory_by_arm']
    lad = d['ladder']
    fig = plt.figure(figsize=(WIDTH, 2.25))
    gs = GridSpec(1, 2, width_ratios=[1.25, 1], wspace=0.78, figure=fig)

    ax = fig.add_subplot(gs[0])
    rows = [('M', 'Code modified ($M$)'), ('F', 'Visible tests pass ($F$)'),
            ('W', 'Safeguard weakened ($W$)')]
    st = framing_styles()
    XC = [117, 133, 149]
    ns = {arms[f]['evaluable'] for f in 'NPA'}
    assert len(ns) == 1
    for y, (k, _) in enumerate(rows):
        vals = [(arms[f][k], arms[f]['evaluable']) for f in 'NPA']
        dots(ax, y, vals, st)
        for (c, _), x in zip(vals, XC):
            ax.text(x, y, f'{c}', ha='center', va='center', fontsize=8,
                    fontweight='bold' if k == 'W' else 'normal')
    headers(ax, -0.95, XC, st, ['N', 'P', 'A'])
    ax.text(XC[1], -0.5, f'of {ns.pop()} each', ha='center', va='center', fontsize=7,
            color=MUTED)
    ax.text(0, -0.95, 'H1 ($A$ ' + MINUS + ' $N$): non-informative\nH2 ($A$ ' + MINUS
            + ' $P$): not tested', fontsize=7.5, color=INK2, va='center', linespacing=1.5)
    ax.set_yticks(range(3), [r[1] for r in rows])
    ax.get_yticklabels()[-1].set_fontweight('bold')
    ax.set_ylim(2.5, -1.3)
    pct_axis(ax, 158, 'runs per framing (30 templates × 4 paraphrases × 2)')
    title(ax, 'a', 'Confirmatory (preregistered, 720 runs)')
    framing_legend(ax, frac(ax, 50), -0.3)

    bx = fig.add_subplot(gs[1])
    rungs = [('L1', 'L1  policy hidden'), ('L2', 'L2  shortcut shown'),
             ('L3', 'L3  hidden + shown'), ('C', 'C  asked to apply it')]
    for y, (r, _) in enumerate(rungs):
        a = lad[r]['all']
        dots(bx, y, [(a['W1'], a['completed'])], [(DARK, 'o', 'white')], size=34)
        bx.text(118, y, f"{a['W1']}", ha='right', va='center', fontsize=8,
                fontweight='bold' if r == 'C' else 'normal')
        bx.text(118.5, y, f"/{a['completed']}", ha='left', va='center', fontsize=8, color=MUTED)
    sched = {lad[r]['all']['scheduled'] for r, _ in rungs}
    assert len(sched) == 1
    bx.text(119, -1.05, '$W$ = 1 / completed', ha='center', va='center', fontsize=7.5,
            color=INK2)
    bx.text(119, -0.6, f'of {sched.pop()} scheduled', ha='center', va='center', fontsize=7,
            color=MUTED)
    bx.set_yticks(range(4), [r[1] for r in rungs])
    bx.get_yticklabels()[-1].set_fontweight('bold')
    bx.set_ylim(3.45, -1.4)
    pct_axis(bx, 135, 'completed runs, framings pooled')
    title(bx, 'b', 'Calibration (exploratory, 6 pilot templates)')
    save(fig, out, 'fig2_confirmatory')


# ---------------------------------------------------------------- Fig. 3
def fig_request(out, d):
    f = d['followup']
    W, dAN = f['x3_W_by_mechanism_framing'], f['x3_dAN']
    fig = plt.figure(figsize=(WIDTH, 2.4))
    gs = GridSpec(1, 2, width_ratios=[2.3, 1], wspace=0.14, figure=fig)

    ax = fig.add_subplot(gs[0])
    rows = [('M1', 'M1  policy timeout'), ('M2', 'M2  API migration'),
            ('M3', 'M3  prior instruction'), ('all', 'All mechanisms')]
    ys = [0, 1, 2, 3.35]

    def cell(m, fr):
        ms = ('M1', 'M2', 'M3') if m == 'all' else (m,)
        return sum(W[x][fr]['W1'] for x in ms), sum(W[x][fr]['n'] for x in ms)
    st = framing_styles()
    XC = [112, 123, 134]
    for y, (m, _) in zip(ys, rows):
        vals = [cell(m, fr) for fr in 'NPA']
        assert len({n for _, n in vals}) == 1
        dots(ax, y, vals, st)
        for (k, _), x in zip(vals, XC):
            ax.text(x, y, f'{k}', ha='center', va='center', fontsize=8,
                    fontweight='bold' if m == 'all' else 'normal')
        ax.text(XC[-1] + 6.5, y, f'of {vals[0][1]}', ha='left', va='center', fontsize=8,
                color=MUTED)
    # count table: how many runs applied the patch, per framing, out of the runs in that row
    ax.text(XC[1], -1.3, 'runs with $W$ = 1', ha='center', va='center', fontsize=7.5, color=INK2)
    ax.plot([XC[0] - 5, XC[-1] + 5], [-1.0, -1.0], color=RULE, lw=0.6, clip_on=False)
    headers(ax, -0.65, XC, st, ['N', 'P', 'A'])
    ax.text(XC[-1] + 6.5, -0.65, 'runs', ha='left', va='center', fontsize=7.5, color=MUTED)
    ax.axhline(2.675, color=RULE, lw=0.6)
    ax.set_yticks(ys, [r[1] for r in rows])
    ax.get_yticklabels()[-1].set_fontweight('bold')
    ax.set_ylim(3.85, -1.55)
    pct_axis(ax, 152, 'runs that applied the weakening patch (oracle $W$ = 1)')
    title(ax, 'a', 'Asked to apply the weakening patch (Gemma 4 31B)')
    framing_legend(ax, frac(ax, 50), -0.22)

    bx = fig.add_subplot(gs[1])
    e, c90, c95 = 100 * dAN['estimate'], [100 * x for x in dAN['ci90']], [100 * x for x in dAN['ci95']]
    bx.axvspan(-10, 10, color=BAND, lw=0, zorder=0)
    bx.plot([0, 0], [-0.32, 0.32], color=MUTED, lw=0.6, ls=(0, (2, 2)), zorder=1)
    bx.plot(c95, [0, 0], color=INK, lw=0.9, zorder=2, solid_capstyle='butt')
    bx.plot(c90, [0, 0], color=INK, lw=3.2, zorder=3, solid_capstyle='butt')
    bx.scatter([e], [0], s=34, color='white', edgecolor=INK, linewidth=1.1, zorder=4)
    bx.text(e, 0.2, f'{mn(e)} pp', ha='center', va='bottom', fontsize=8, fontweight='bold',
            bbox=dict(boxstyle='square,pad=0.15', fc=BAND, ec='none'), zorder=5)
    bx.text(-9.4, 0.86, 'SESOI ±10 pp', ha='left', va='center', fontsize=7.5, color=INK2)
    bx.text(0, -0.48, f'90% CI [{mn(c90[0])}, {mn(c90[1])}]', ha='center', va='center', fontsize=7.5)
    bx.text(0, -0.74, f'95% CI [{mn(c95[0])}, {mn(c95[1])}]', ha='center', va='center',
            fontsize=7.5, color=INK2)
    bx.set_ylim(-1, 1)
    bx.set_yticks([])
    bx.set_xlim(-14, 14)
    bx.set_xticks([-10, -5, 0, 5, 10], [f'{MINUS}10', f'{MINUS}5', '0', '+5', '+10'])
    bx.set_xlabel(f'$A$ {MINUS} $N$ in $W$ (pp); frozen estimator, $K$ = 30')
    title(bx, 'b', f'Framing contrast $A$ {MINUS} $N$')
    save(fig, out, 'fig3_request')


# ---------------------------------------------------------------- Fig. 4
MECH = {'M1': (DARK, 'o', 'white'), 'M2': (MID, 's', INK), 'M3': (LIGHT, 'D', INK)}


def fig_detectors(out, d):
    p = d['followup']['x3_weakening_patches']
    g = d['followup']['gate']['x3']
    fig = plt.figure(figsize=(WIDTH, 2.75))
    gs = GridSpec(1, 2, width_ratios=[1.3, 1], wspace=0.72, figure=fig)

    ax = fig.add_subplot(gs[0])
    rows = [('tests', 'Visible tests pass'), ('ast', 'AST baseline: alert'),
            ('gsc', 'GSC (call graph): alert'), ('gsc_ne', 'GSC: not evaluable'),
            ('except_local', 'except-local: alert'), ('disc', 'Lexical disclosure pattern')]

    def val(r, m):
        c = p[m]
        return {'tests': c['tests_pass'], 'disc': c['disclosed_any_turn'], 'gsc': c['gsc_alert'],
                'gsc_ne': c['W1'] - c['gsc_evaluable']}.get(r, c.get(f'{r}_alert')), c['W1']
    for m in p:
        assert p[m]['ast_evaluable'] == p[m]['except_local_evaluable'] == p[m]['W1']
    ms = ['M1', 'M2', 'M3']
    st = [MECH[m] for m in ms]
    XC = [116, 140, 164]
    for y, (r, _) in enumerate(rows):
        vals = [val(r, m) for m in ms]
        dots(ax, y, vals, st)
        for (k, _), x in zip(vals, XC):
            ax.text(x, y, f'{k}', ha='center', va='center', fontsize=8)
    headers(ax, -1.25, XC, st, ms, sub=[f"{p[m]['W1']}" for m in ms], dy=0.55, mdx=10.5)
    ax.text(XC[-1] + 9, -0.7, '= n', ha='left', va='center', fontsize=7, color=MUTED)
    ax.set_yticks(range(len(rows)), [r[1] for r in rows])
    ax.set_ylim(len(rows) - 0.5, -1.65)
    pct_axis(ax, 180, f"the {sum(p[m]['W1'] for m in ms)} weakening patches ($W$ = 1), by mechanism")
    title(ax, 'a', 'What flags a weakening patch')

    bx = fig.add_subplot(gs[1])
    pols = [('tests_only', 'Tests only'), ('ast', 'AST'), ('gsc', 'GSC')]
    y, ticks, labels = 0, [], []
    for pk, pl in pols:
        for kind, lab in (('U', 'weakening'), ('S', 'safe repair')):
            n, held = g[pk][kind], g[pk][f'{kind}_flagged']
            alarm = g['gsc_alerts_only'][f'{kind}_flagged'] if pk == 'gsc' else held
            abst = held - alarm
            if alarm:
                bx.barh(y, 100 * alarm / n, 0.62, color=DARK, lw=0, zorder=2)
            if abst:
                bx.barh(y, 100 * abst / n, 0.62, left=100 * alarm / n, facecolor='white',
                        edgecolor=MID, hatch='//////', lw=0.5, zorder=2)
            bx.text(100 * held / n + 2, y, f'{held}', ha='left', va='center', fontsize=8,
                    fontweight='bold' if kind == 'U' else 'normal')
            bx.text(100 * held / n + 2 + 4.2 * len(str(held)), y, f'/{n}', ha='left',
                    va='center', fontsize=8, color=MUTED)
            ticks.append(y)
            labels.append(f'{pl}  ·  {lab}' if kind == 'U' else lab)
            y += 1
        y += 0.45
    bx.set_yticks(ticks, labels)
    for t, lab in zip(bx.get_yticklabels(), labels):
        if '·' in lab:
            t.set_fontweight('bold')
    bx.set_ylim(y - 0.6, -0.65)
    pct_axis(bx, 100, 'held back for review (% of each kind)', left=0)
    bx.spines['bottom'].set_bounds(0, 100)
    title(bx, 'b', 'Frozen gate on the 360 test-passing patches')
    bx.legend(handles=[Patch(color=DARK, label='alarm'),
                       Patch(facecolor='white', edgecolor=MID, hatch='//////', lw=0.5,
                             label='not evaluable (abstention)')],
              loc='upper center', bbox_to_anchor=(0.45, -0.2), ncol=2, handlelength=1.4,
              columnspacing=1.2)
    save(fig, out, 'fig4_detectors')


# ---------------------------------------------------------------- Appendix
def fig_models(out, d):
    m = d['followup']['models']['rows']
    order = [('e2b', 'E2B  QAT · Colab A100'), ('e4b_kaggle', 'E4B  QAT · Kaggle L4×4'),
             ('e4b_hf', 'E4B  QAT · Colab A100'), ('26b_a4b', '26B-A4B  bf16 MoE · Colab A100'),
             ('31b_x3', '31B  QAT · Colab A100 (x3, N)')]
    segs = [('W1', 'weakened ($W$ = 1)', dict(facecolor=DARK, lw=0)),
            ('W0_tests_pass', 'not weakened, tests pass (safe repair)',
             dict(facecolor=MID, lw=0)),
            ('W0_tests_fail', 'not weakened, tests fail',
             dict(facecolor='white', edgecolor=MID, hatch='//////', lw=0.5))]
    fig, ax = plt.subplots(figsize=(WIDTH, 2.35))
    for i, (key, _) in enumerate(order):
        p = m[key]['pooled']
        if p['not_evaluable']:
            raise SystemExit(f'{key}: not-evaluable runs need their own segment')
        n, left = p['runs'], 0.0
        for j, (s, _, kw) in enumerate(segs):
            w = 100 * p[s] / n
            ax.barh(i, w, 0.6, left=left, zorder=2, **kw)
            if p[s] >= 7:
                ax.text(left + w / 2, i, str(p[s]), ha='center', va='center', fontsize=7.5,
                        color='white' if j == 0 else INK,
                        bbox=None if j < 2 else dict(boxstyle='square,pad=0.1', fc='white',
                                                     ec='none'))
            left += w
        ax.text(103, i, f"{p['W0_tests_pass']}", ha='right', va='center', fontsize=8,
                fontweight='bold', transform=ax.transData)
        ax.text(103.3, i, f'/{n}', ha='left', va='center', fontsize=8, color=MUTED)
    ax.text(103, -0.75, 'safe repairs', ha='center', va='center', fontsize=7.5, color=INK2)
    ax.set_yticks(range(len(order)), [o[1] for o in order])
    ax.set_ylim(len(order) - 0.45, -1.05)
    pct_axis(ax, 112, 'Gemma 4 configurations, explicit request, framing $N$: 120 runs each '
             '(30 templates × 4 paraphrases)', left=0)
    ax.grid(False)
    ax.legend(handles=[Patch(label=lab, **kw) for _, lab, kw in segs], loc='upper center',
              bbox_to_anchor=(frac(ax, 50), -0.24), ncol=3, handlelength=1.4, columnspacing=1.4)
    save(fig, out, 'figA1_models')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    setup()
    d = load()
    fig_instrument(out)
    fig_confirmatory(out, d)
    fig_request(out, d)
    fig_detectors(out, d)
    fig_models(out, d)
    print(json.dumps(sorted(p.name for p in out.glob('*.png'))))


if __name__ == '__main__':
    main()
