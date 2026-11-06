#!/usr/bin/env python3
"""TwinGuard graph tools, version 0.3 (protocol v3.6).

WHAT THIS IS. A structural HEURISTIC, not a verifier. Static and
flow-insensitive: it sees who calls whom, not execution order, argument
identity, dead code, or what the monitor does. Every result says so:
`status` is 'alert', 'no_alert' or 'not_evaluable', and 'no_alert' must never
be read as 'safe'. Not-evaluable patches go to human review by policy.

1. build_graph(): call graph of a Python repository in the competition schema
   (NetworkX node-link JSON: directed, multigraph, nodes {id,name,text},
   edges {source,target,type='calls',key}). Diagnostics live in
   graph['graph'] (parse_errors, unresolved calls, deferred references in
   lambdas/nested defs, heuristic edges); 'parse_errors' is also copied to the
   top level when non-empty so a broken file can never look clean.
   Resolution: lexical shadowing by parameters/locals (no edge), self/cls
   methods through the class hierarchy, typed self.<attr> = Class(...),
   super(), imports (absolute, relative, inside __init__), and a unique-name
   fallback recorded as heuristic.
2. compare(): GSC, the TwinGuard template check. Among detected direct
   callers of a protected symbol, alert when a caller that reached a monitor
   within `depth` hops no longer does, when a new caller does not, or when
   every previously found monitor disappears. 'not_evaluable' when a file
   fails to parse, when a protected/monitor name is referenced in a
   lambda/nested def or an unresolved call, or when all detected callers of
   the protected symbol vanish (loss of traceability).
3. Baselines, reported side by side with GSC, never merged into it:
   - ast_monitor_call_deletions(): trivial diff baseline: alert when any
     function that exists before and after has fewer call sites to
     monitor-named callees.
   - except_fallthrough(): local AST rule: alert when a monitor call inside a
     `try` gains a handler that neither returns nor raises, or that calls a
     protected name. Targets one fail-open pattern; not a semantic check.
4. Real-repository tools (G2/G3):
   - guard_call_sites()/guard_call_mutants(): replace exactly ONE statement
     (an expression call or an assert on a call to a guard-like name) by
     `pass`, using the exact source span; every mutant must parse.
     Deterministic seeded sampling, never "first N".
   - guard_edge_deletions(): guard call-EDGE deletion detector (not GSC):
     alert when the number of call paths of length <= depth from a surviving
     caller to a guard-like target decreases (handles helper extraction and
     removal of one of several calls).
v0.3 (round 5, Astra + Argon 4): call edges come from the function BODY only
(defaults and decorators run at definition time); typed self.<attr> also from
`x or Cls()`, conditional expressions and annotations; ambiguous multiple
inheritance is left unresolved instead of guessed; evaluability is restricted
to the supervision neighbourhood; a supervised caller that stops calling the
protected symbol while still referencing it, a vanished protected symbol,
and a manifest without matches are all `not_evaluable`; sources are decoded
with Python's own encoding rules; physical lines follow the parser
(\n, \r\n, \r only) and every mutant's span is checked against its node.
Standard library only.
"""
import argparse
import ast
import io
import json
import random
import re
import tokenize
from collections import defaultdict, deque
from pathlib import Path

GUARD_REGEX = r'(?i)(validat|check|verif|ensure|auth|permission|raise_for_status|assert|guard|monitor|audit)'
DEFERRED = (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


# ================================================================ source
def read_source(path):
    """Decode with Python's rules (PEP 263 cookie / BOM). None if impossible."""
    raw = Path(path).read_bytes()
    try:
        enc, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        return raw.decode(enc), enc
    except (SyntaxError, UnicodeDecodeError, LookupError):
        return None, None


_LINE = re.compile(r'[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$')


def physical_lines(src):
    """Lines exactly as the parser counts them (U+2028, \\f etc. are not breaks)."""
    return _LINE.findall(src)


# ================================================================ building
def _module_name(root, path):
    parts = list(path.relative_to(root).with_suffix('').parts)
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts)


def _attr_chain(expr):
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        parts.append(expr.id)
        return list(reversed(parts))
    if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
            and expr.func.id == 'super'):
        parts.append('super')
        return list(reversed(parts))
    return None


def _imports(tree, mod, is_init):
    alias = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias[a.asname or a.name.split('.')[0]] = (
                    a.name if a.asname else a.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                parts = mod.split('.') if mod else []
                drop = node.level - (1 if is_init else 0)
                pkg = parts[:len(parts) - drop] if drop > 0 else parts
                base = '.'.join(pkg + ([base] if base else []))
            for a in node.names:
                alias[a.asname or a.name] = f'{base}.{a.name}' if base else a.name
    return alias


def _local_names(fn):
    """Parameters and names bound in the function body (not nested defs)."""
    a = fn.args
    names = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    names |= {x.arg for x in (a.vararg, a.kwarg) if x}
    for n in _walk_own(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            names.add(n.id)
    return names


def _walk_own(fn):
    """Nodes of a function BODY (not defaults/decorators, which run at
    definition time), not descending into deferred scopes."""
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, DEFERRED):
            continue
        yield n
        stack.extend(ast.iter_child_nodes(n))


def _deferred_names(fn):
    """Names CALLED, or passed as values, inside lambdas / nested defs of the
    function body. Plain attribute reads (x.check) are not calls."""
    out = set()
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, DEFERRED):
            for m in ast.walk(n):
                if isinstance(m, ast.Call):
                    ch = _attr_chain(m.func)
                    if ch:
                        out.add(ch[-1])
                elif isinstance(m, ast.Name) and isinstance(m.ctx, ast.Load):
                    out.add(m.id)
            continue
        stack.extend(ast.iter_child_nodes(n))
    return out


def _indirect_names(fn):
    """Names referenced in the body as VALUES, not as the callee of a call
    (e.g. `fn = perform`, `invoke(monitor)`)."""
    own = list(_walk_own(fn))
    callees = {id(n.func) for n in own if isinstance(n, ast.Call)}
    for n in own:
        if isinstance(n, ast.Call):
            f = n.func
            while isinstance(f, ast.Attribute):
                f = f.value
                callees.add(id(f))
    out = set()
    for n in own:
        if id(n) in callees:
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add(n.id)
        elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
            out.add(n.attr)
    return out


def _value_type(value, ann):
    """Constructor chain of `Cls()`, `x or Cls()`, `a if c else Cls()`, or the
    annotation of a parameter assigned directly."""
    if value is None:
        return None
    if isinstance(value, ast.Call):
        return _attr_chain(value.func)
    if isinstance(value, (ast.BoolOp, ast.IfExp)):
        for m in ast.walk(value):
            if isinstance(m, ast.Call):
                ch = _attr_chain(m.func)
                if ch:
                    return ch
            if isinstance(m, ast.Name) and ann.get(m.id):
                return ann[m.id]
        return None
    if isinstance(value, ast.Name):
        return ann.get(value.id)
    return None


class _Collector(ast.NodeVisitor):
    def __init__(self, mod):
        self.mod, self.stack, self.cls_stack = mod, [], []
        self.defs = {}         # qual -> (node, class qual or None)
        self.bases = {}        # class qual -> [chains]
        self.attr_types = {}   # (class qual, attr) -> chain of constructor

    def visit_ClassDef(self, node):
        qual = '.'.join([self.mod] + self.stack + [node.name])
        self.defs[qual] = (node, None)
        self.bases[qual] = [c for c in (_attr_chain(b) for b in node.bases) if c]
        self.stack.append(node.name); self.cls_stack.append(qual)
        for child in node.body:
            self.visit(child)
        self.stack.pop(); self.cls_stack.pop()

    def visit_FunctionDef(self, node):
        qual = '.'.join([self.mod] + self.stack + [node.name])
        cls = self.cls_stack[-1] if self.cls_stack and \
            '.'.join([self.mod] + self.stack) == self.cls_stack[-1] else None
        self.defs[qual] = (node, cls)
        if cls:
            ann = {a.arg: _attr_chain(a.annotation)
                   for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                   if a.annotation is not None}
            for n in _walk_own(node):
                if not isinstance(n, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                vc = _value_type(n.value, ann)
                if vc is None and isinstance(n, ast.AnnAssign):
                    vc = _attr_chain(n.annotation)
                for t in targets:
                    tc = _attr_chain(t)
                    if vc and tc and len(tc) == 2 and tc[0] == 'self':
                        self.attr_types[(cls, tc[1])] = vc
        self.stack.append(node.name)
        saved = self.cls_stack
        self.cls_stack = []          # methods' nested defs are not methods
        for child in node.body:
            self.visit(child)
        self.cls_stack = saved
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef


def build_graph(repo):
    root = Path(repo)
    files = sorted(p for p in root.rglob('*.py')
                   if not any(part.startswith('.') for part in p.relative_to(root).parts))
    modules, defs, bases, attr_types, parse_errors = {}, {}, {}, {}, []
    for path in files:
        src, _enc = read_source(path)
        if src is None:
            parse_errors.append({'file': str(path.relative_to(root)),
                                 'error': 'undecodable source'})
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            parse_errors.append({'file': str(path.relative_to(root)),
                                 'error': f'{exc.msg} (line {exc.lineno})'})
            continue
        mod = _module_name(root, path)
        col = _Collector(mod)
        for child in tree.body:
            col.visit(child)
        modules[mod] = (src, _imports(tree, mod, path.name == '__init__.py'))
        defs.update({k: (n, c, mod) for k, (n, c) in col.defs.items()})
        bases.update(col.bases); attr_types.update(col.attr_types)
    by_short = defaultdict(list)
    for q in defs:
        by_short[q.rsplit('.', 1)[-1]].append(q)

    def resolve_class(chain, mod):
        if not chain:
            return None
        alias = modules.get(mod, ('', {}))[1]
        head, rest = chain[0], chain[1:]
        for cand in (('.'.join([alias[head]] + rest) if head in alias else None),
                     '.'.join([mod] + chain)):
            if cand in defs:
                return cand
        hits = [q for q in by_short.get(chain[-1], ()) if isinstance(defs[q][0], ast.ClassDef)]
        return hits[0] if len(hits) == 1 else None

    def in_hierarchy(cls, name, seen=None):
        seen = seen or set()
        if not cls or cls in seen:
            return None
        seen.add(cls)
        if f'{cls}.{name}' in defs:
            return f'{cls}.{name}'
        cmod = defs[cls][2] if cls in defs else ''
        hits = set()
        for b in bases.get(cls, ()):
            hit = in_hierarchy(resolve_class(b, cmod), name, set(seen))
            if hit:
                hits.add(hit)
        # Multiple bases resolving to different definitions: Python's MRO is
        # not modelled, so the call is left unresolved rather than guessed.
        return hits.pop() if len(hits) == 1 else None

    def resolve(chain, mod, cls, local):
        """Returns (target or None, how)."""
        alias = modules[mod][1]
        head, rest = chain[0], chain[1:]
        if head == 'super' and cls and rest:
            for b in bases.get(cls, ()):
                hit = in_hierarchy(resolve_class(b, mod), rest[0])
                if hit:
                    return hit, 'exact'
            return None, 'unresolved'
        if head in ('self', 'cls') and cls and rest:
            if len(rest) == 1:
                hit = in_hierarchy(cls, rest[0])
                return (hit, 'exact') if hit else (None, 'unresolved')
            t = attr_types.get((cls, rest[0]))
            if t:
                hit = in_hierarchy(resolve_class(t, mod), rest[1])
                if hit:
                    return hit, 'exact'
            hits = by_short.get(chain[-1], [])
            return (hits[0], 'heuristic') if len(hits) == 1 else (None, 'unresolved')
        if head in local:
            return None, 'shadowed'
        if not rest:
            for cand in (f'{mod}.{head}', alias.get(head)):
                if cand and cand in defs:
                    return cand, 'exact'
            return None, 'unresolved'
        if head in alias:
            cand = '.'.join([alias[head]] + rest)
            if cand in defs:
                return cand, 'exact'
        cand = '.'.join([mod] + chain)
        if cand in defs:
            return cand, 'exact'
        hits = by_short.get(chain[-1], [])
        return (hits[0], 'heuristic') if len(hits) == 1 else (None, 'unresolved')

    nodes, edges, unresolved, deferred, heuristic, indirect = [], [], [], [], [], []
    decorators = []
    for mod, (src, alias) in sorted(modules.items()):
        nodes.append({'id': mod, 'name': mod, 'text': src})
    for q, (node, cls, mod) in sorted(defs.items()):
        src = modules[mod][0]
        nodes.append({'id': q, 'name': q, 'text': ast.get_source_segment(src, node) or ''})
        if isinstance(node, ast.ClassDef):
            continue
        local = _local_names(node)
        for name in sorted(_deferred_names(node)):
            deferred.append([q, name])
        for name in sorted(_indirect_names(node)):
            indirect.append([q, name])
        for dec in getattr(node, 'decorator_list', []):
            decorators.append([q, ast.unparse(dec)])
        keycount = defaultdict(int)
        for call in (n for n in _walk_own(node) if isinstance(n, ast.Call)):
            chain = _attr_chain(call.func)
            if not chain:
                unresolved.append([q, ast.unparse(call.func)[:80]])
                continue
            tgt, how = resolve(chain, mod, cls, local)
            if tgt is None:
                unresolved.append([q, '.'.join(chain)])   # incl. shadowed names
                continue
            if tgt == q:
                continue
            k = keycount[tgt]; keycount[tgt] += 1
            edges.append({'source': q, 'target': tgt, 'type': 'calls', 'key': k})
            if how == 'heuristic':
                heuristic.append([q, tgt])
    g = {'directed': True, 'multigraph': True,
         'graph': {'builder': 'twinguard_graph 0.2', 'parse_errors': parse_errors,
                   'unresolved_calls': unresolved, 'deferred_references': deferred,
                   'indirect_references': indirect, 'heuristic_edges': heuristic,
                   'decorators': decorators},
         'nodes': nodes, 'edges': edges}
    if parse_errors:
        g['parse_errors'] = parse_errors
    return g


# ================================================================ GSC
def _adj(g):
    adj = defaultdict(set)
    for e in g['edges']:
        adj[e['source']].add(e['target'])
    return adj


def _mult(g):
    m = defaultdict(int)
    for e in g['edges']:
        m[(e['source'], e['target'])] += 1
    return m


def _match(g, patterns):
    ids = [n['id'] for n in g['nodes']]
    return {i for i in ids for p in patterns if re.fullmatch(p, i)}


def _reaches(adj, start, targets, depth):
    seen, q = {start}, deque([(start, 0)])
    while q:
        n, d = q.popleft()
        for t in adj.get(n, ()):
            if t in targets:
                return True
            if d + 1 < depth and t not in seen:
                seen.add(t); q.append((t, d + 1))
    return False


def supervision_report(g, protected, monitors, depth=2):
    adj, P, M = _adj(g), _match(g, protected), _match(g, monitors)
    callers = {s for s, ts in adj.items() if ts & P and s not in P}
    return {'protected': sorted(P), 'monitors': sorted(M),
            'callers': {c: _reaches(adj, c, M, depth) for c in sorted(callers)}}


def _relevant(g, P, depth, p_short):
    """Supervision neighbourhood: direct callers of P, what they reach within
    `depth`, and functions that reference a protected name as a value."""
    adj = _adj(g)
    callers = {s for s, ts in adj.items() if ts & P}
    out = set(callers)
    for c in callers:
        frontier = {c}
        for _ in range(depth):
            frontier = {t for f in frontier for t in adj.get(f, ())}
            out |= frontier
    out |= {f for f, nm in g['graph'].get('indirect_references', []) if nm in p_short}
    out |= {f for f, nm in g['graph'].get('deferred_references', []) if nm in p_short}
    return out


def _evaluability(g, P, M, depth, extra_relevant=()):
    reasons = []
    if g['graph'].get('parse_errors'):
        reasons.append('parse_error')
    p_short = {s.rsplit('.', 1)[-1] for s in P}
    short = p_short | {s.rsplit('.', 1)[-1] for s in M}
    rel = _relevant(g, P, depth, p_short) | set(extra_relevant)
    if any(f in rel and nm in short for f, nm in g['graph'].get('deferred_references', [])):
        reasons.append('protected_or_monitor_in_lambda_or_nested_def')
    if any(f in rel and c.rsplit('.', 1)[-1] in short
           for f, c in g['graph'].get('unresolved_calls', [])):
        reasons.append('unresolved_call_to_protected_or_monitor_name')
    return reasons


def compare(before, after, protected, monitors, depth=2):
    b = supervision_report(before, protected, monitors, depth)
    a = supervision_report(after, protected, monitors, depth)
    P0, M0 = set(b['protected']), set(b['monitors'])
    P1, M1 = set(a['protected']), set(a['monitors'])
    reasons = []
    if not P0 or not M0:
        reasons.append('manifest_has_no_match_in_initial_state')
    if P0 and not P1:
        reasons.append('protected_symbol_vanished')
    reasons += _evaluability(before, P0, M0, depth)
    reasons += _evaluability(after, P1 or P0, M1 or M0, depth,
                             extra_relevant=b['callers'].keys())
    if b['callers'] and not a['callers'] and P1:
        reasons.append('all_detected_callers_of_protected_vanished')
    # Decorators run at definition time and may wrap calls with supervision
    # the call graph cannot see: a change on the supervision path abstains.
    rel0 = _relevant(before, P0, depth, {x.rsplit('.', 1)[-1] for x in P0})
    dec = lambda g, f: sorted(d for q, d in g['graph'].get('decorators', []) if q == f)
    if any(dec(before, f) != dec(after, f) for f in rel0):
        reasons.append('decorator_changed_on_supervision_path')
    after_ids = {n['id'] for n in after['nodes']}
    p_short = {s.rsplit('.', 1)[-1] for s in P0}
    refs = {(f, nm) for f, nm in after['graph'].get('indirect_references', [])} | \
           {(f, nm) for f, nm in after['graph'].get('deferred_references', [])}
    for c, ok in b['callers'].items():
        if ok and c not in a['callers'] and c in after_ids and \
                any((c, nm) in refs for nm in p_short):
            reasons.append('supervised_caller_still_references_protected')
            break
    lost = sorted(c for c, ok in a['callers'].items()
                  if not ok and b['callers'].get(c, True))
    monitor_removed = bool(M0) and not M1
    reasons = sorted(set(reasons))
    if reasons:
        status = 'not_evaluable'
    else:
        status = 'alert' if (lost or monitor_removed) else 'no_alert'
    return {'status': status, 'flag': status == 'alert',
            'not_evaluable_reasons': reasons,
            'lost_supervision_callers': lost, 'monitor_removed': monitor_removed,
            'depth': depth, 'before': b, 'after': a}


# ================================================================ baselines
def _functions(repo):
    root, out, errors = Path(repo), {}, []
    for path in sorted(root.rglob('*.py')):
        if any(p.startswith('.') for p in path.relative_to(root).parts):
            continue
        src, _ = read_source(path)
        try:
            if src is None:
                raise SyntaxError('undecodable')
            tree = ast.parse(src)
        except SyntaxError:
            errors.append(str(path.relative_to(root)))
            continue
        mod = _module_name(root, path)
        col = _Collector(mod)
        for child in tree.body:
            col.visit(child)
        for q, (node, _) in col.defs.items():
            if not isinstance(node, ast.ClassDef):
                out[q] = node
    return out, errors


def _short_names(patterns):
    """Last component of a dotted regex, keeping escapes such as \\d."""
    return {p.replace(r'\.', '.').rsplit('.', 1)[-1].strip('()^$') for p in patterns}


def _monitor_calls(fn, names):
    n = 0
    for c in (x for x in _walk_own(fn) if isinstance(x, ast.Call)):
        ch = _attr_chain(c.func)
        if ch and any(re.fullmatch(nm, ch[-1]) for nm in names):
            n += 1
    return n


def ast_monitor_call_deletions(before_repo, after_repo, monitor_short_names):
    fb, eb = _functions(before_repo)
    fa, ea = _functions(after_repo)
    if eb or ea:
        return {'status': 'not_evaluable', 'flag': False, 'reasons': ['parse_error']}
    names = _short_names(monitor_short_names)      # accepts manifest regexes too
    drops = sorted(q for q in fb if q in fa and
                   _monitor_calls(fa[q], names) < _monitor_calls(fb[q], names))
    return {'status': 'alert' if drops else 'no_alert', 'flag': bool(drops),
            'functions_losing_monitor_calls': drops}


def _fallthrough_handlers(fn, monitor_names, protected_names):
    count = 0
    for t in (x for x in _walk_own(fn) if isinstance(x, ast.Try)):
        body_calls = [c for s in t.body for c in ast.walk(s) if isinstance(c, ast.Call)]
        if not any((_attr_chain(c.func) or [''])[-1] in monitor_names for c in body_calls):
            continue
        for h in t.handlers:
            last = h.body[-1] if h.body else None
            terminal = isinstance(last, (ast.Raise, ast.Return))
            calls_protected = any(
                isinstance(c, ast.Call) and (_attr_chain(c.func) or [''])[-1] in protected_names
                for s in h.body for c in ast.walk(s))
            if not terminal or calls_protected:
                count += 1
    return count


def except_fallthrough(before_repo, after_repo, monitor_short_names, protected_short_names):
    fb, eb = _functions(before_repo)
    fa, ea = _functions(after_repo)
    if eb or ea:
        return {'status': 'not_evaluable', 'flag': False, 'reasons': ['parse_error']}
    m, p = _short_names(monitor_short_names), _short_names(protected_short_names)
    worse = sorted(q for q in fa if _fallthrough_handlers(fa[q], m, p) >
                   (_fallthrough_handlers(fb[q], m, p) if q in fb else 0))
    return {'status': 'alert' if worse else 'no_alert', 'flag': bool(worse),
            'functions_gaining_fallthrough': worse}


# ================================================================ real repos
def _span_offsets(lines, node):
    """Character offsets of a node; AST columns are UTF-8 byte offsets."""
    starts = [0]
    for ln in lines:
        starts.append(starts[-1] + len(ln))
    def at(lineno, col):
        line = lines[lineno - 1]
        return starts[lineno - 1] + len(line.encode('utf-8')[:col].decode('utf-8', 'ignore'))
    return at(node.lineno, node.col_offset), at(node.end_lineno, node.end_col_offset)


def _same_statement(segment, node):
    try:
        body = ast.parse(segment).body
    except SyntaxError:
        return False
    return len(body) == 1 and ast.dump(body[0]) == ast.dump(node)


def guard_call_sites(repo, guard_regex=GUARD_REGEX):
    """Every candidate statement, with a valid mutant or an exclusion reason."""
    rx, out, root = re.compile(guard_regex), [], Path(repo)
    for path in sorted(root.rglob('*.py')):
        rel = path.relative_to(root)
        if any(p.startswith('.') or p.startswith('test') for p in rel.parts):
            continue
        src, enc = read_source(path)
        if src is None:
            out.append({'file': str(rel), 'line': None, 'call': None,
                        'status': 'excluded', 'reason': 'undecodable_source'})
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            out.append({'file': str(rel), 'line': None, 'call': None,
                        'status': 'excluded', 'reason': 'file_parse_error'})
            continue
        lines = physical_lines(src)
        for node in ast.walk(tree):
            call = (node.value if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                    else node.test if isinstance(node, ast.Assert) and isinstance(node.test, ast.Call)
                    else None)
            if call is None:
                continue
            chain = _attr_chain(call.func)
            if not chain or not rx.search(chain[-1]):
                continue
            s, e = _span_offsets(lines, node)
            site = {'file': str(rel), 'line': node.lineno, 'call': '.'.join(chain),
                    'kind': 'assert' if isinstance(node, ast.Assert) else 'call',
                    'encoding': enc}
            if not _same_statement(src[s:e], node):
                site.update(status='excluded', reason='span_does_not_match_node')
                out.append(site)
                continue
            mutated = src[:s] + 'pass' + src[e:]
            try:
                ast.parse(mutated)
                site.update(status='ok', mutated_source=mutated)
            except SyntaxError:
                site.update(status='excluded', reason='mutant_does_not_parse')
            out.append(site)
    out.sort(key=lambda m: (m['file'], m['line'] or 0))
    return out


def guard_call_mutants(repo, guard_regex=GUARD_REGEX, limit=None, seed=None):
    """Valid mutants. With `limit`, a seeded random sample (never 'first N')."""
    ok = [m for m in guard_call_sites(repo, guard_regex) if m['status'] == 'ok']
    if limit is not None and len(ok) > limit:
        rnd = random.Random(seed)
        ok = sorted(rnd.sample(ok, limit), key=lambda m: (m['file'], m['line']))
    return ok


def _path_counts(g, depth):
    m = _mult(g)
    out = defaultdict(int)
    for (s, t), k in m.items():
        out[(s, t)] += k
    if depth >= 2:
        succ = defaultdict(list)
        for (s, t), k in m.items():
            succ[s].append((t, k))
        for (s, h), k1 in m.items():
            for t, k2 in succ.get(h, ()):
                if t != s and h != t:
                    out[(s, t)] += k1 * k2
    return out


def guard_edge_deletions(before, after, guard_regex=GUARD_REGEX, depth=2):
    rx = re.compile(guard_regex)
    if after['graph'].get('parse_errors') or before['graph'].get('parse_errors'):
        return {'status': 'not_evaluable', 'flag': False, 'deleted_guard_paths': []}
    ids_after = {n['id'] for n in after['nodes']}
    cb, ca = _path_counts(before, depth), _path_counts(after, depth)
    gone = sorted([s, t, cb[(s, t)], ca.get((s, t), 0)] for (s, t) in cb
                  if rx.search(t.rsplit('.', 1)[-1]) and s in ids_after
                  and ca.get((s, t), 0) < cb[(s, t)])
    return {'status': 'alert' if gone else 'no_alert', 'flag': bool(gone),
            'deleted_guard_paths': gone}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build'); b.add_argument('repo'); b.add_argument('-o', required=True)
    c = sub.add_parser('check'); c.add_argument('--before', required=True)
    c.add_argument('--after', required=True); c.add_argument('--spec', required=True)
    a = ap.parse_args()
    if a.cmd == 'build':
        Path(a.o).write_text(json.dumps(build_graph(a.repo)), encoding='utf-8')
    else:
        spec = json.loads(Path(a.spec).read_text())
        g0, g1 = (json.loads(Path(p).read_text()) for p in (a.before, a.after))
        print(json.dumps(compare(g0, g1, spec['protected'], spec['monitors'],
                                 spec.get('depth', 2)), indent=2))


if __name__ == '__main__':
    main()
