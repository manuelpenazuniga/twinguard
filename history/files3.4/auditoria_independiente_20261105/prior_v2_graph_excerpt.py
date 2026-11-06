# Reemplazo para las secciones de construcción y chequeo en twinguard_graph.py (L44-L260)

class _Defs(ast.NodeVisitor):
    def __init__(self, mod, src):
        self.mod, self.src, self.stack = mod, src, []
        self.defs = {}            # id -> (ast node, class id or None)
        self.bases = {}           # class id -> list of base expr chains
        self.attr_types = {}      # (class id, attr) -> target class chain

    def _add(self, node):
        qual = '.'.join([self.mod] + self.stack + [node.name])
        cls = '.'.join([self.mod] + self.stack) if self.stack and \
            isinstance(self._parent, ast.ClassDef) else None
        self.defs[qual] = (node, cls)
        return qual

    def visit_ClassDef(self, node):
        self._parent = None
        qual = self._add(node)
        self.bases[qual] = [c for b in node.bases if (c := _attr_chain(b))]
        self.stack.append(node.name)
        for child in node.body:
            self._parent = node
            self.visit(child)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        self._parent = getattr(self, '_parent', None)
        qual = self._add(node)
        cls = self.defs[qual][1]
        if cls:  # C.1: track self.<attr> = <Class>(...) assignments
            for n in ast.walk(node):
                if isinstance(n, (ast.Assign, ast.AnnAssign)):
                    targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                    if isinstance(n.value, ast.Call) and (vc := _attr_chain(n.value.func)):
                        for t in targets:
                            if (tc := _attr_chain(t)) and len(tc) == 2 and tc[0] == 'self':
                                self.attr_types[(cls, tc[1])] = vc
        self.stack.append(node.name)
        saved = self._parent
        for child in node.body:
            self._parent = node
            self.visit(child)
        self._parent = saved
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef


def _imports(tree, mod, is_init=False):
    alias = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias[a.asname or a.name.split('.')[0]] = a.name if a.asname else a.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:  # C.3: preserve package name when inside __init__.py
                parts = mod.split('.') if mod else []
                drop = node.level - (1 if is_init else 0)
                pkg = parts[:max(0, len(parts) - drop)] if drop > 0 else parts
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
    # C.4: support super().method(...)
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == 'super':
        parts.append('super')
        return list(reversed(parts))
    return None


def _own_calls(fn_node):
    """Calls in a function body (including lambdas and decorators), excluding
    nested defs/classes and dead statements after unconditional return/raise."""
    out = []
    if isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        # C.4: include bare and called decorators as calls of fn_node
        for dec in fn_node.decorator_list:
            if isinstance(dec, (ast.Name, ast.Attribute)):
                out.append(ast.Call(func=dec, args=[], keywords=[]))
            elif isinstance(dec, ast.Call) and isinstance(dec.func, (ast.Name, ast.Attribute)):
                out.append(dec)

    def walk_block(stmts):
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            walk_node(stmt)
            # C.6: stop walking sequential statements after unconditional exit
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                break

    def walk_node(node):
        # C.2: do NOT skip ast.Lambda; calls inside a lambda belong to the enclosing function
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.Call):
            out.append(node)
        for field, val in ast.iter_fields(node):
            if field == 'decorator_list':
                continue
            if isinstance(val, list):
                if val and isinstance(val[0], ast.stmt):
                    walk_block(val)
                else:
                    for item in val:
                        if isinstance(item, ast.AST):
                            walk_node(item)
            elif isinstance(val, ast.AST):
                walk_node(val)

    if isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        walk_block(fn_node.body)
    return out


def build_graph(repo):
    root = Path(repo)
    files = sorted(p for p in root.rglob('*.py')
                   if not any(part.startswith('.') for part in p.parts))
    modules, all_defs, all_bases, all_attr_types = {}, {}, {}, {}
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
        modules[mod] = (tree, src, _imports(tree, mod, path.name == '__init__.py'), v.defs)
        all_defs.update({k: (n, c, mod) for k, (n, c) in v.defs.items()})
        all_bases.update(v.bases)
        all_attr_types.update(v.attr_types)
    by_short = defaultdict(list)
    for q in all_defs:
        by_short[q.rsplit('.', 1)[-1]].append(q)

    def resolve_class(chain, mod, alias):
        if not chain:
            return None
        head, rest = chain[0], chain[1:]
        for cand in ('.'.join([alias[head]] + rest) if head in alias else None,
                     '.'.join([mod] + chain)):
            if cand and cand in all_defs:
                return cand
        hits = by_short.get(chain[-1], [])
        return hits[0] if len(hits) == 1 else None

    def find_in_hierarchy(cls_id, method_name, seen=None):
        seen = seen or set()
        if not cls_id or cls_id in seen:
            return None
        seen.add(cls_id)
        if f'{cls_id}.{method_name}' in all_defs:
            return f'{cls_id}.{method_name}'
        _, _, cmod = all_defs.get(cls_id, (None, None, ''))
        calias = modules[cmod][2] if cmod in modules else {}
        for bchain in all_bases.get(cls_id, ()):
            if hit := find_in_hierarchy(resolve_class(bchain, cmod, calias), method_name, seen):
                return hit
        return None

    def resolve(chain, mod, cls, alias):
        head, rest = chain[0], chain[1:]
        if head == 'super' and cls and rest:
            for bchain in all_bases.get(cls, ()):
                if hit := find_in_hierarchy(resolve_class(bchain, mod, alias), rest[0]):
                    return hit
        if head in ('self', 'cls') and cls and rest:
            if len(rest) == 1 and (hit := find_in_hierarchy(cls, rest[0])):
                return hit
            if len(rest) >= 2 and (tchain := all_attr_types.get((cls, rest[0]))):
                if hit := find_in_hierarchy(resolve_class(tchain, mod, alias), rest[1]):
                    return hit
        if not rest:
            for cand in (find_in_hierarchy(cls, head) if cls else None,
                         f'{mod}.{head}', alias.get(head)):
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
        return hits[0] if len(hits) == 1 else None
