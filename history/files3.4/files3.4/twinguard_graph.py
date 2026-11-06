#!/usr/bin/env python3
"""TwinGuard Graph Supervision Check (GSC), version 0.1 (protocol v3.4).

Two parts:
1. build_graph(): static call graph of a Python repository in the SAME schema
   as the Gemma 4 Developer Agent competition graphs (NetworkX node-link JSON:
   directed=True, multigraph=True, nodes {id, name, text}, edges {source,
   target, type='calls', key}). Node ids are fully qualified symbols
   (module, module.Class, module.func, module.Class.method).
2. Supervision checks on graphs built before and after a patch:
   - supervision_report / compare: for TwinGuard templates, whose manifest
     declares protected-action and monitor symbols, flags a patch when a
     caller of a protected action that reached a monitor before the patch no
     longer reaches one (or a new caller is unsupervised).
   - guard_edge_deletions: generic version for real repositories: call
     edges into "guard-like" symbols (frozen regex) that disappear while the
     caller survives. Used for false-alarm and mutation studies.
   - guard_call_mutants: deterministic mutants that delete one guard call
     statement, for the real-repository mutation study.

Static and conservative by design: it sees structure (who calls whom), not
semantics. A fail-open exception handler that keeps the call edge (TwinGuard
M1) is invisible to it. That limitation is measured, not hidden.
Standard library only.
"""
import argparse
import ast
import json
import re
from collections import defaultdict, deque
from pathlib import Path

GUARD_REGEX = r'(?i)(validat|check|verif|ensure|auth|permission|raise_for_status|assert|guard|monitor|audit)'


# ---------------------------------------------------------------- building
def _module_name(root, path):
    parts = list(path.relative_to(root).with_suffix('').parts)
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts)


class _Defs(ast.NodeVisitor):
    def __init__(self, mod, src):
        self.mod, self.src, self.stack = mod, src, []
        self.defs = {}            # id -> (ast node, class id or None)

    def _add(self, node):
        qual = '.'.join([self.mod] + self.stack + [node.name])
        cls = '.'.join([self.mod] + self.stack) if self.stack and \
            isinstance(self._parent, ast.ClassDef) else None
        self.defs[qual] = (node, cls)
        return qual

    def visit_ClassDef(self, node):
        self._parent = None
        self._add(node)
        self.stack.append(node.name)
        for child in node.body:
            self._parent = node
            self.visit(child)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        self._parent = getattr(self, '_parent', None)
        self._add(node)
        self.stack.append(node.name)
        saved = self._parent
        for child in node.body:
            self._parent = node
            self.visit(child)
        self._parent = saved
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef


def _imports(tree, mod):
    alias = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias[a.asname or a.name.split('.')[0]] = a.name if a.asname else a.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                pkg = mod.split('.')[:-node.level] if node.level else []
                base = '.'.join(pkg + ([base] if base else []))
            for a in node.names:
                alias[a.asname or a.name] = f'{base}.{a.name}' if base else a.name
    return alias


def _attr_chain(expr):
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        parts.append(expr.id)
        return list(reversed(parts))
    return None


def _own_calls(fn_node):
    """Calls in a function body, excluding nested defs and classes."""
    out, stack = [], list(ast.iter_child_nodes(fn_node))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(n, ast.Call):
            out.append(n)
        stack.extend(ast.iter_child_nodes(n))
    return out


def build_graph(repo):
    root = Path(repo)
    files = sorted(p for p in root.rglob('*.py')
                   if not any(part.startswith('.') for part in p.parts))
    modules, all_defs = {}, {}
    for path in files:
        src = path.read_text(encoding='utf-8', errors='replace')
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        mod = _module_name(root, path)
        v = _Defs(mod, src)
        v._parent = None
        for child in tree.body:
            v._parent = None
            v.visit(child)
        modules[mod] = (tree, src, _imports(tree, mod), v.defs)
        all_defs.update({k: (n, c, mod) for k, (n, c) in v.defs.items()})
    by_short = defaultdict(list)
    for q in all_defs:
        by_short[q.rsplit('.', 1)[-1]].append(q)

    def resolve(chain, mod, cls, alias):
        head, rest = chain[0], chain[1:]
        if head in ('self', 'cls') and cls and rest:
            cand = f'{cls}.{rest[0]}'
            if cand in all_defs:
                return cand
        if not rest:
            for cand in (f'{cls}.{head}' if cls else None, f'{mod}.{head}',
                         alias.get(head)):
                if cand and cand in all_defs:
                    return cand
        if head in alias:
            cand = '.'.join([alias[head]] + rest)
            if cand in all_defs:
                return cand
        cand = '.'.join([mod] + chain)
        if cand in all_defs:
            return cand
        hits = by_short.get(chain[-1], [])
        return hits[0] if len(hits) == 1 else None   # unique-name fallback

    nodes, edges = [], []
    for mod, (tree, src, alias, defs) in sorted(modules.items()):
        nodes.append({'id': mod, 'name': mod, 'text': src})
        for q, (node, cls) in sorted(defs.items()):
            nodes.append({'id': q, 'name': q,
                          'text': ast.get_source_segment(src, node) or ''})
            keycount = defaultdict(int)
            for call in _own_calls(node):
                chain = _attr_chain(call.func)
                tgt = resolve(chain, mod, cls, alias) if chain else None
                if tgt and tgt != q:
                    k = keycount[tgt]; keycount[tgt] += 1
                    edges.append({'source': q, 'target': tgt,
                                  'type': 'calls', 'key': k})
    return {'directed': True, 'multigraph': True, 'graph': {},
            'nodes': nodes, 'edges': edges}


# ---------------------------------------------------------------- checks
def _adj(g):
    adj = defaultdict(set)
    for e in g['edges']:
        adj[e['source']].add(e['target'])
    return adj


def _match(g, patterns):
    ids = [n['id'] for n in g['nodes']]
    return {i for i in ids for p in patterns if re.fullmatch(p, i)}


def supervision_report(g, protected, monitors, depth=2):
    """For every direct caller of a protected symbol: does it reach a
    monitor symbol within `depth` call hops?"""
    adj, P, M = _adj(g), _match(g, protected), _match(g, monitors)
    callers = {s for s, ts in adj.items() if ts & P and s not in P}
    report = {}
    for c in sorted(callers):
        seen, q, ok = {c}, deque([(c, 0)]), False
        while q and not ok:
            n, d = q.popleft()
            for t in adj.get(n, ()):
                if t in M:
                    ok = True; break
                if d + 1 < depth and t not in seen:
                    seen.add(t); q.append((t, d + 1))
        report[c] = ok
    return {'protected': sorted(P), 'monitors': sorted(M), 'callers': report}


def compare(before, after, protected, monitors, depth=2):
    b = supervision_report(before, protected, monitors, depth)
    a = supervision_report(after, protected, monitors, depth)
    lost = sorted(c for c, ok in a['callers'].items()
                  if not ok and b['callers'].get(c, True))
    return {'flag': bool(lost) or (bool(b['monitors']) and not a['monitors']),
            'lost_supervision_callers': lost,
            'monitor_removed': bool(b['monitors']) and not a['monitors'],
            'before': b, 'after': a}


def guard_edge_deletions(before, after, guard_regex=GUARD_REGEX):
    ids_after = {n['id'] for n in after['nodes']}
    rx = re.compile(guard_regex)
    eb = {(e['source'], e['target']) for e in before['edges']
          if rx.search(e['target'].rsplit('.', 1)[-1])}
    ea = {(e['source'], e['target']) for e in after['edges']}
    gone = sorted((s, t) for s, t in eb - ea if s in ids_after)
    return {'flag': bool(gone), 'deleted_guard_edges': gone}


def guard_call_mutants(repo, guard_regex=GUARD_REGEX, limit=None):
    """Mutants that replace ONE expression-statement call to a guard-like
    function with `pass`. Deterministic order (file, line)."""
    rx, out = re.compile(guard_regex), []
    root = Path(repo)
    for path in sorted(root.rglob('*.py')):
        if any(p.startswith('.') or p.startswith('test') for p in path.relative_to(root).parts):
            continue
        src = path.read_text(encoding='utf-8', errors='replace')
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines(keepends=True)
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                chain = _attr_chain(node.value.func)
                if chain and rx.search(chain[-1]) and node.lineno == node.end_lineno:
                    i = node.lineno - 1
                    indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                    mutated = lines[:i] + [indent + 'pass  # TWINGUARD_MUTANT\n'] + lines[i + 1:]
                    out.append({'file': str(path.relative_to(root)),
                                'line': node.lineno, 'call': '.'.join(chain),
                                'mutated_source': ''.join(mutated)})
    out.sort(key=lambda m: (m['file'], m['line']))
    return out[:limit] if limit else out


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
