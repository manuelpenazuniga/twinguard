"""Graph tools backed by twinguard_graph.build_graph (same node-link schema as the
competition graphs). README 6.3 replica: get_code_neighbors, get_code_subgraph.

Freshness: the graph is rebuilt whenever the workspace's Python sources change (cache
keyed by a content hash of every *.py file), so the cache is effectively per
template x framing x state (protocol 7.1). Ordering is deterministic: neighbors are
sorted by node id; subgraph edges by (from, to, type).
"""
import hashlib
import shutil
import tempfile
from pathlib import Path

from twinguard_graph import build_graph

from harness import contract as C


def own_py_files(root):
    """Regular .py files physically inside root. Symlinks are ignored, so the controller
    never reads files outside the workspace on the agent's behalf (e.g. an oracle)."""
    root = Path(root)
    out = []
    for p in sorted(root.rglob('*.py')):
        rel = p.relative_to(root)
        if any(part.startswith('.') for part in rel.parts):
            continue
        if any((root / Path(*rel.parts[:i + 1])).is_symlink() for i in range(len(rel.parts))):
            continue
        if p.is_file():
            out.append(rel)
    return out


def tree_hash(root):
    h = hashlib.sha256()
    for rel in own_py_files(root):
        h.update(rel.as_posix().encode() + b'\0' + (Path(root) / rel).read_bytes() + b'\0')
    return h.hexdigest()


class GraphIndex:
    def __init__(self, root):
        self.root = root
        self._key = None
        self._graph = None
        self.builds = 0

    def graph(self):
        key = tree_hash(self.root)
        if key != self._key:
            with tempfile.TemporaryDirectory(prefix='g_') as tmp:
                for rel in own_py_files(self.root):
                    (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(self.root / rel, Path(tmp) / rel)
                self._graph = build_graph(tmp)
            self._key = key
            self.builds += 1
        return self._graph

    # README 6.3: exact -> '.', ';', '/' suffix -> case-insensitive -> substring.
    # Ties inside a tier resolve to the lexicographically first id (our choice).
    def resolve(self, name):
        ids = sorted(n['id'] for n in self.graph()['nodes'])
        name = str(name).strip()
        if name in ids:
            return name
        tiers = (
            lambda i: any(i.endswith(sep + name) for sep in '.;/'),
            lambda i: i.lower() == name.lower(),
            lambda i: name.lower() in i.lower(),
        )
        for tier in tiers:
            hits = [i for i in ids if tier(i)]
            if hits:
                return hits[0]
        return None

    def neighbors(self, node, edge_type=None, max_neighbors=50):
        resolved = self.resolve(node)
        if resolved is None:
            return C.error(C.NodeNotFound, f'node not found in code graph: {node}')
        found = set()
        for e in self.graph()['edges']:
            if edge_type and e['type'].lower() != str(edge_type).lower():
                continue
            if e['source'] == resolved:
                found.add(e['target'])
            if e['target'] == resolved:
                found.add(e['source'])
        names = sorted(found)[:max(0, int(max_neighbors))]
        out, used, truncated = [], 0, False
        for n in names:
            if used + len(n) > C.MAX_STDOUT_CHARS:
                truncated = True
                break
            out.append(n)
            used += len(n)
        return {'status': 'ok', 'node': resolved, 'neighbors': out, 'count': len(found),
                'is_truncated': truncated}

    def subgraph(self, nodes):
        resolved = []
        for n in nodes:
            r = self.resolve(n)
            if r is not None and r not in resolved:
                resolved.append(r)
        if not resolved:
            return C.error(C.SubgraphError, f'none of the nodes were found: {list(nodes)}')
        keep = set(resolved)
        edges = sorted({(e['source'], e['target'], e['type']) for e in self.graph()['edges']
                        if e['source'] in keep and e['target'] in keep})
        node_list = sorted(keep)
        edge_list = [{'from': a, 'to': b, 'type': t} for a, b, t in edges]
        truncated = False
        while len(C.dumps(node_list)) + len(C.dumps(edge_list)) > C.MAX_STDOUT_CHARS:
            truncated = True
            if edge_list:
                edge_list.pop()
            elif node_list:
                node_list.pop()
            else:
                break
        return {'status': 'ok', 'nodes': node_list, 'edges': edge_list,
                'node_count': len(keep), 'edge_count': len(edges), 'is_truncated': truncated}
