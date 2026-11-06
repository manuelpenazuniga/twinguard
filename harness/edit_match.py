"""3-tier replacement engine for edit_file (replica of adk-eval-core apply_replacement,
from the README 6.2 description): exact -> flexible (per-line stripped, re-indented)
-> regex (tokens around code delimiters joined by flexible whitespace)."""
import re

DELIMS = r'([()\:\[\]{}>=<])'


class EditError(Exception):
    pass


def _indent(line):
    return line[:len(line) - len(line.lstrip())]


def _exact(content, old):
    n = content.count(old)
    return n, (lambda new, multiple: content.replace(old, new) if multiple
               else content.replace(old, new, 1))


def _strip_blank_edges(lines):
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return lines


def _flexible(content, old):
    old_lines = _strip_blank_edges(old.split('\n'))
    if not old_lines:
        return 0, None
    lines = content.split('\n')
    target = [l.strip() for l in old_lines]
    k = len(target)
    starts, i = [], 0
    while i + k <= len(lines):
        if [l.strip() for l in lines[i:i + k]] == target:
            starts.append(i)
            i += k
        else:
            i += 1
    if not starts:
        return 0, None
    old_base = min((_indent(l) for l in old_lines if l.strip()), key=len, default='')

    def apply(new, multiple):
        out, prev = [], 0
        for s in (starts if multiple else starts[:1]):
            base = _indent(lines[s])
            new_lines = []
            for l in new.split('\n'):
                body = l[len(old_base):] if l.startswith(old_base) else l.lstrip()
                new_lines.append(base + body if l.strip() else '')
            out += lines[prev:s] + new_lines
            prev = s + k
        return '\n'.join(out + lines[prev:])
    return len(starts), apply


def _regex(content, old):
    tokens = [t for t in re.split(DELIMS + r'|\s+', old) if t]
    if not tokens:
        return 0, None
    pat = re.compile(r'\s*'.join(re.escape(t) for t in tokens))
    matches = list(pat.finditer(content))
    if not matches:
        return 0, None

    def apply(new, multiple):
        out, prev = [], 0
        for m in (matches if multiple else matches[:1]):
            out += [content[prev:m.start()], new]
            prev = m.end()
        return ''.join(out) + content[prev:]
    return len(matches), apply


def apply_replacement(content, old, new, allow_multiple=False):
    """Return (new_content, occurrences, strategy) or raise EditError."""
    if old == '':
        raise EditError('old_string must not be empty')
    content = content.replace('\r\n', '\n')
    old = old.replace('\r\n', '\n')
    new = new.replace('\r\n', '\n')
    for name, tier in (('exact', _exact), ('flexible', _flexible), ('regex', _regex)):
        n, apply = tier(content, old)
        if n == 0:
            continue
        if n > 1 and not allow_multiple:
            raise EditError(f'old_string matched {n} occurrences ({name}); provide more '
                            'context to make it unique or set allow_multiple=true')
        return apply(new, allow_multiple), n, name
    raise EditError('old_string not found in file')
