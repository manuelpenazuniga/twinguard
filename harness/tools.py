"""The 8 tools (README 6, minus search_similar_code) with the official budget gate.

ToolBox.dispatch(name, raw_arguments) -> JSON string, exactly what the model sees.
run_command, read_file, edit_file, write_file and the graph tools count toward
budget.tool_calls; submit_patch and get_status are free (README 6.1).
"""
import difflib
import inspect
import json
import time

from harness import contract as C
from harness.edit_match import EditError, apply_replacement
from harness.graph_tools import GraphIndex
from harness.workspace import WorkspaceError, files_changed

COUNTED = {'run_command', 'read_file', 'edit_file', 'write_file',
           'get_code_neighbors', 'get_code_subgraph'}
FREE = {'submit_patch', 'get_status'}
TOOL_NAMES = ('run_command', 'read_file', 'edit_file', 'write_file', 'submit_patch',
              'get_status', 'get_code_neighbors', 'get_code_subgraph')


def _coerce(value, annotation):
    """README 6.2/6.3: LLM string-encoded ints/bools/lists are coerced."""
    if value is None:
        return None
    if annotation in (int, 'int | None') and isinstance(value, str):
        return int(value.strip())
    if annotation is bool and isinstance(value, str):
        v = value.strip().lower()
        if v in ('true', '1', 'yes'):
            return True
        if v in ('false', '0', 'no'):
            return False
        raise ValueError(f'cannot interpret {value!r} as a boolean')
    if annotation is list and isinstance(value, str):
        s = value.strip()
        if s.startswith('['):
            return json.loads(s)
        return [x.strip() for x in s.split(',') if x.strip()]
    return value


class ToolBox:
    def __init__(self, workspace, budget, clock=time.monotonic):
        self.ws = workspace
        self.budget = budget
        self.clock = clock
        self.graph = GraphIndex(workspace.root, workspace)
        self.tool_calls_used = 0
        self.patch_submitted = False
        self.submitted_patch = ''
        self.start = None
        self.budget_exhausted = False

    # ------------------------------------------------------------ session
    def start_session(self):
        self.start = self.clock()

    def elapsed(self):
        return 0.0 if self.start is None else self.clock() - self.start

    def time_remaining(self):
        return self.budget.time_minutes * 60 - self.elapsed()

    def calls_remaining(self):
        return self.budget.tool_calls - self.tool_calls_used

    # ------------------------------------------------------------ dispatch
    def dispatch(self, name, raw_arguments):
        method = getattr(self, f't_{name}', None) if name in TOOL_NAMES else None
        if method is None:
            return C.plugin_error('ValueError', f'Tool {name!r} not found. Available tools: '
                                  + ', '.join(TOOL_NAMES))
        try:
            args = raw_arguments if isinstance(raw_arguments, dict) else \
                json.loads(raw_arguments or '{}')
            if not isinstance(args, dict):
                raise TypeError('tool arguments must be a JSON object')
            sig = inspect.signature(method)
            unknown = set(args) - set(sig.parameters)
            if unknown:
                raise TypeError(f'{name}() got unexpected arguments: {sorted(unknown)}')
            bound = {}
            for p in sig.parameters.values():
                if p.name in args:
                    bound[p.name] = _coerce(args[p.name], p.annotation)
                elif p.default is inspect.Parameter.empty:
                    raise TypeError(f'{name}() missing required argument: {p.name!r}')
        except (ValueError, TypeError) as exc:
            return C.plugin_error(type(exc).__name__, str(exc))

        # swegemma check_budget order: tool calls, then session time (budget errors never
        # carry the low-budget warning)
        if name in COUNTED and self.calls_remaining() <= 0:
            self.budget_exhausted = True
            return C.dumps(C.error(C.BudgetExhausted,
                                   f'Tool call budget exhausted ({self.budget.tool_calls} calls)'))
        if self.time_remaining() <= 0:
            self.budget_exhausted = True
            return C.dumps(C.error(C.TimeoutExceeded, 'Session time budget exhausted '
                                   f'({self.budget.time_minutes} minutes)'))
        if name in COUNTED:
            self.tool_calls_used += 1
        try:
            result = method(**bound)
        except WorkspaceError as exc:
            result = C.error(exc.error_type, str(exc))
        if name not in COUNTED:
            return C.dumps(result)
        return self._finish(result)

    def _finish(self, result):
        if 'budget_warning' not in result and self.budget.tool_calls >= C.BUDGET_WARNING_MIN_TOTAL and \
                self.calls_remaining() <= C.BUDGET_WARNING_REMAINING:
            result = dict(result)
            result['budget_warning'] = (
                f'Only {max(0, self.calls_remaining())} tool call(s) remaining '
                f'({self.tool_calls_used}/{self.budget.tool_calls} used). '
                'Finalize your edits and call submit_patch soon.')
        return C.dumps(result)

    # ------------------------------------------------------------ tools
    def t_run_command(self, command: str):
        timeout = min(C.COMMAND_TIMEOUT_SECONDS,
                      max(C.MIN_COMMAND_TIMEOUT, int(self.time_remaining())))
        r = self.ws.run(command, timeout)
        out, _ = C.truncate(r['stdout'])
        err, _ = C.truncate(r['stderr'])
        if r['timed_out']:
            return C.error(C.TimeoutExceeded, f'Command timed out after {timeout} seconds')
        if r['exit_code'] != 0:
            return C.error(C.CommandError, err if err else out,
                           stdout=out, stderr=err, exit_code=r['exit_code'])
        return {'status': 'ok', 'stdout': out, 'stderr': err, 'exit_code': 0}

    def t_read_file(self, filepath: str, start_line: int = None, end_line: int = None):
        full = self.ws.resolve(filepath)
        if self.ws.kind(full) != 'file':
            return C.error(C.FileNotFound, f'file not found: {filepath}')
        try:
            lines = self.ws.read_text(full).splitlines(keepends=True)
        except OSError as exc:
            return C.error(C.FileReadError, f'cannot read {filepath}: {exc}')
        total = len(lines)
        s = max(1, start_line or 1)
        e = total if end_line is None else min(end_line, total)
        if total and s > total:
            return C.error(C.ValidationError, f'start_line {s} exceeds file length {total}')
        if e < s and total:
            return C.error('ValueError', f'start_line ({s}) cannot be greater than end_line ({e})',
                           **{})
        chunk, chars, truncated = [], 0, False
        for i in range(s - 1, e):
            if len(chunk) >= C.MAX_FILE_LINES or chars + len(lines[i]) > C.MAX_FILE_CHARS:
                truncated = True
                break
            chunk.append(lines[i])
            chars += len(lines[i])
        last = s - 1 + len(chunk)
        return {'status': 'ok', 'filepath': self.ws.rel(full), 'content': ''.join(chunk),
                'start_line': s, 'end_line': last, 'total_lines': total,
                'is_truncated': truncated}

    def t_edit_file(self, filepath: str, old_string: str, new_string: str,
                    allow_multiple: bool = False):
        full = self.ws.resolve(filepath)
        if self.ws.kind(full) != 'file':
            return C.error(C.FileEditError, f'file not found: {filepath}')
        try:
            before = self.ws.read_text(full)
        except OSError as exc:
            return C.error(C.FileEditError, f'cannot read {filepath}: {exc}')
        if before == '':
            return C.error(C.FileEditError, f'file is empty: {filepath}')
        try:
            after, n, strategy = apply_replacement(before, old_string, new_string,
                                                   allow_multiple)
        except EditError as exc:
            return C.error(C.FileEditError, str(exc))
        try:
            self.ws.write_text(full, after)
        except OSError as exc:
            return C.error(C.FileEditError, f'cannot write {filepath}: {exc}')
        rel = self.ws.rel(full)
        diff = ''.join(difflib.unified_diff(
            before.replace('\r\n', '\n').splitlines(keepends=True),
            after.splitlines(keepends=True), f'a/{rel}', f'b/{rel}'))
        diff, truncated = C.truncate(diff)
        return {'status': 'ok', 'filepath': rel, 'occurrences': n, 'strategy': strategy,
                'diff': diff, 'is_truncated': truncated}

    def t_write_file(self, filepath: str, content: str):
        full = self.ws.resolve(filepath)
        if self.ws.kind(full) == 'dir':
            return C.error(C.FileWriteError, f'[Errno 21] Is a directory: {filepath}')
        try:
            self.ws.write_text(full, content)
        except OSError as exc:
            return C.error(C.FileWriteError, f'cannot write {filepath}: {exc}')
        return {'status': 'ok', 'filepath': self.ws.rel(full), 'size': len(content)}

    def t_submit_patch(self):
        patch = self.ws.diff()
        self.submitted_patch = patch
        self.patch_submitted = True
        return {'status': 'ok', 'patch_size': len(patch),
                'files_changed': files_changed(patch)}

    def t_get_status(self):
        return {'status': 'ok', 'tool_calls_used': self.tool_calls_used,
                'patch_submitted': self.patch_submitted,
                'patch_size': len(self.submitted_patch),
                'tool_calls_remaining': max(0, self.calls_remaining()),
                'max_tool_calls': self.budget.tool_calls,
                'time_seconds_remaining': round(max(0.0, self.time_remaining()), 1),
                'max_time_minutes': self.budget.time_minutes,
                'agent_elapsed_seconds': round(self.elapsed(), 1),
                'max_turns': self.budget.turns,
                'command_timeout_seconds': C.COMMAND_TIMEOUT_SECONDS}

    def t_get_code_neighbors(self, node: str, edge_type: str = None, max_neighbors: int = 50):
        return self.graph.neighbors(node, edge_type, max_neighbors)

    def t_get_code_subgraph(self, nodes: list):
        return self.graph.subgraph(nodes)


# OpenAI function schemas (frozen with the contract).
def _fn(name, desc, props, required):
    return {'type': 'function', 'function': {
        'name': name, 'description': desc,
        'parameters': {'type': 'object', 'properties': props, 'required': required}}}


TOOL_SCHEMAS = [
    _fn('run_command', 'Execute a shell command with /bin/bash -c inside /workspace. '
        'Output is truncated to 5000 characters.',
        {'command': {'type': 'string'}}, ['command']),
    _fn('read_file', 'Read a file under /workspace with 1-indexed inclusive line slicing '
        '(at most 150 lines and 10000 characters per call).',
        {'filepath': {'type': 'string'}, 'start_line': {'type': 'integer'},
         'end_line': {'type': 'integer'}}, ['filepath']),
    _fn('edit_file', 'Replace old_string with new_string in an existing file under '
        '/workspace. old_string must match exactly one location unless allow_multiple is true.',
        {'filepath': {'type': 'string'}, 'old_string': {'type': 'string'},
         'new_string': {'type': 'string'}, 'allow_multiple': {'type': 'boolean'}},
        ['filepath', 'old_string', 'new_string']),
    _fn('write_file', 'Create or overwrite a file under /workspace, creating parent '
        'directories.', {'filepath': {'type': 'string'}, 'content': {'type': 'string'}},
        ['filepath', 'content']),
    _fn('submit_patch', 'Submit the current changes in /workspace as the final patch. '
        'Call it last, once your changes are complete and verified.', {}, []),
    _fn('get_status', 'Return remaining tool calls, time and patch status.', {}, []),
    _fn('get_code_neighbors', 'Find callers and callees of a symbol node (e.g. '
        '`pkg.module.Class.method` or `Class.method`).',
        {'node': {'type': 'string'}, 'edge_type': {'type': 'string'},
         'max_neighbors': {'type': 'integer'}}, ['node']),
    _fn('get_code_subgraph', 'Get the induced call subgraph connecting a list of symbol '
        'nodes.', {'nodes': {'type': 'array', 'items': {'type': 'string'}}}, ['nodes']),
]
