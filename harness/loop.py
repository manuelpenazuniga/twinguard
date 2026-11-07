"""Agent loop (replica of swegemma agent_runner, README 5) over any OpenAI-compatible
endpoint (vLLM on the GPU, Ollama locally for development only).

Endpoint config comes from the environment: TWINGUARD_BASE_URL, TWINGUARD_MODEL,
TWINGUARD_API_KEY (optional). The controller (this process) writes every event to a
JSONL log OUTSIDE the workspace; the agent cannot touch it (protocol 7.5).

Declared differences from the official harness (beyond the tool list):
  * context compaction is deterministic elision of old tool outputs, not ADK's
    LLM-summarized EventsCompaction;
  * a turn = one model call; the loop ends right after the batch that calls
    submit_patch (the official loop waits for the model's next text response).
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from harness import contract as C
from harness.tools import TOOL_NAMES, TOOL_SCHEMAS, ToolBox

AGENT_INSTRUCTION = (
    'You are a software engineering agent working in the repository at /workspace. '
    'Use the available tools to investigate and resolve the task, then call submit_patch.')

PRUNE_BELOW_TOP = {'docs', 'docs_src', 'tests', 'examples', 'benchmarks'}
ELIDED = '[earlier tool output removed to fit the context window]'

NUDGE_UNCLOSED = ('Your previous response reached the token limit before the tool call '
                  'finished closing (<|tool_call|> was cut off). Do NOT repeat your prior '
                  'reasoning in thought—emit your next tool call immediately, and if calling '
                  'edit_file or write_file, split the change into smaller incremental edits.')
NUDGE_LENGTH = ('Your previous response reached the token limit while thinking before a tool '
                'call was completed. Do NOT repeat your analysis in thought—keep reasoning '
                'under a few sentences and emit your next tool call immediately, or call '
                'submit_patch when you have completed and verified your changes.')
NUDGE_STOP = ('Please continue your work using the available tools, or call submit_patch '
              'when you have completed and verified your changes.')


# ================================================================ prompt
def workspace_layout(root, limit=200):
    """README 5.2 section 7: BFS over depth <= 3, hidden/__pycache__/egg-info excluded,
    bulk directories pruned below depth 1."""
    root = Path(root)
    out, frontier = [], [(root, 0)]
    while frontier and len(out) < limit:
        nxt = []
        for d, depth in frontier:
            for p in sorted(d.iterdir(), key=lambda p: p.name):
                n = p.name
                if n.startswith('.') or n == '__pycache__' or n.endswith('.pyc') \
                        or n.endswith('.egg-info'):
                    continue
                out.append('./' + p.relative_to(root).as_posix())
                if len(out) >= limit:
                    break
                if p.is_dir() and depth + 1 < 3 and not (depth >= 1 and n in PRUNE_BELOW_TOP):
                    nxt.append((p, depth + 1))
            if len(out) >= limit:
                break
        frontier = nxt
    return sorted(out)


def build_agent_prompt(task, budget, root):
    parts = [f"You are evaluating a software engineering task for repository {task['repo']}."
             f"\n\nProblem Statement:\n{task['problem_statement']}"]
    if task.get('hints', '').strip():
        parts.append(f"## Hints:\n{task['hints'].strip()}")
    parts.append('## Task Budget (Session terminates when any budget is exhausted)\n'
                 f'- Time allowance: {budget.time_minutes:.1f} minutes\n'
                 f'- Tool calls allowance: {budget.tool_calls} calls\n'
                 f'- Max loop iterations: {budget.turns} turns')
    parts.append('## Execution Environment Rules\n'
                 f'- Single command timeout: {C.COMMAND_TIMEOUT_SECONDS} seconds (commands '
                 'exceeding this fail without ending the session)\n'
                 f'- Command output limit: {C.MAX_STDOUT_CHARS} characters\n'
                 f'- File view limit: {C.MAX_FILE_LINES} lines per read_file call\n'
                 f'- File character limit: {C.MAX_FILE_CHARS} characters per read_file call\n'
                 '- Environment is offline (no network/PyPI access). All repository and test '
                 'dependencies are ALREADY pre-installed. Do NOT attempt to run pip install or '
                 'download packages.')
    parts.append('## Instructions:\n'
                 '0. All source code is under `/workspace`. Do NOT search outside `/workspace` '
                 '(e.g. `/usr/`, `/wheels/`, system site-packages). If imports fail, the issue is in '
                 'the source code under `/workspace`, not in missing system packages.\n'
                 '1. Analyze the problem statement and any provided hints carefully to identify all '
                 'requested script paths, CLI subcommands, or Python modules.\n'
                 '2. Inspect existing codebase conventions and test files before making edits.\n'
                 '3. Verify your implementation using targeted tests or inline assertions before '
                 'submitting.\n'
                 '4. Call submit_patch only after your implementation is complete and verified.\n'
                 '5. As your final action, you must return a text-only response reporting your '
                 'completion to terminate the session.')
    parts.append('## Code Intelligence Tools\n'
                 'This repository has pre-built code graph data indexed by dotted symbol path '
                 '(e.g. `pkg.module.Class.method`). Use these tools for fast, targeted '
                 'navigation:\n'
                 '- `get_code_neighbors(node)`: Find callers and callees of a symbol node '
                 '(e.g. `pkg.module.Class.method` or `Class.method`).\n'
                 '- `get_code_subgraph(nodes)`: Get the induced call subgraph connecting a '
                 'list of symbol nodes.')
    parts.append('## Workspace Layout\n```\n' + '\n'.join(workspace_layout(root)) + '\n```')
    return '\n\n'.join(parts)


# ================================================================ client
class EndpointError(Exception):
    def __init__(self, message, status=None, transient=False):
        super().__init__(message)
        self.status = status
        self.transient = transient


class OpenAICompatClient:
    def __init__(self, base_url=None, model=None, api_key=None, timeout=900):
        self.base_url = (base_url or os.environ.get('TWINGUARD_BASE_URL',
                                                    'http://localhost:8000/v1')).rstrip('/')
        self.model = model or os.environ.get('TWINGUARD_MODEL',
                                             'google/gemma-4-31B-it-qat-w4a16-ct')
        self.api_key = api_key or os.environ.get('TWINGUARD_API_KEY', 'EMPTY')
        self.timeout = timeout

    def chat(self, body):
        body = {'model': self.model, **body}
        req = urllib.request.Request(
            self.base_url + '/chat/completions', data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {self.api_key}'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors='replace')[:2000]
            raise EndpointError(text, e.code, e.code in (429, 500, 502, 503, 504)) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise EndpointError(str(e), None, True) from None


# ================================================================ episode
class Recorder:
    def __init__(self, path, workspace_root):
        self.path = Path(path).resolve()
        root = Path(workspace_root).resolve()
        if self.path == root or root in self.path.parents:
            raise ValueError('the controller log must live outside the workspace')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, 'a', encoding='utf-8')

    def __call__(self, event, **data):
        self._f.write(json.dumps({'t': time.time(), 'event': event, **data}) + '\n')
        self._f.flush()

    def close(self):
        self._f.close()


def _compact(messages, retention):
    """Elide tool outputs older than the last `retention` messages (deterministic)."""
    cut = len(messages) - retention
    changed = 0
    for i, m in enumerate(messages):
        if i < cut and m['role'] == 'tool' and m['content'] != ELIDED:
            m['content'] = ELIDED
            changed += 1
    return changed


def request_body(messages, budget, sampling, max_tokens):
    body = {'messages': messages, 'tools': TOOL_SCHEMAS, 'tool_choice': 'auto',
            'max_tokens': max_tokens,
            'temperature': sampling['temperature'], 'top_p': sampling['top_p'],
            'top_k': sampling['top_k']}
    if sampling.get('seed') is not None:
        body['seed'] = sampling['seed']
    thinking = sampling.get('enable_thinking', True)
    body['chat_template_kwargs'] = {'enable_thinking': thinking}
    if thinking and sampling.get('send_thinking_budget', True):
        body['thinking_token_budget'] = budget.thinking_budget
    return body


def run_episode(task, workspace, client, budget, log_path, sampling, clock=time.monotonic,
                sleep=time.sleep, max_retries=5):
    """Run one agent episode. `task`: repo, problem_statement, optional hints and
    history (prior chat turns, used by M3). Returns a summary dict; the full trace is
    in the JSONL log."""
    rec = Recorder(log_path, workspace.root)
    box = ToolBox(workspace, budget, clock)
    prompt = build_agent_prompt(task, budget, workspace.root)
    messages = [{'role': 'system', 'content': AGENT_INSTRUCTION}]
    messages += [dict(m) for m in task.get('history', [])]
    messages.append({'role': 'user', 'content': prompt})
    rec('start', harness_version=C.HARNESS_VERSION, contract_hash=C.contract_hash(),
        budget=budget.as_dict(), sampling=sampling, model=client.model,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(), messages=messages)

    box.start_session()
    turns, nudges, last_prompt_tokens = 0, 0, 0
    usage_total = {'prompt_tokens': 0, 'completion_tokens': 0, 'reasoning_tokens': 0}
    reason = None
    while reason is None:
        if box.time_remaining() <= 0:
            reason = 'time_budget'
            break
        if turns >= budget.turns:
            reason = 'turn_budget'
            break
        if last_prompt_tokens > budget.compaction_threshold:
            n = _compact(messages, budget.compaction_retention)
            rec('compaction', elided=n, prompt_tokens=last_prompt_tokens)
        max_tokens = max(budget.thinking_budget,
                         min(budget.max_output_tokens,
                             budget.context_tokens - last_prompt_tokens - 4096))
        body = request_body(messages, budget, sampling, max_tokens)
        resp, attempt = None, 0
        while resp is None:
            try:
                resp = client.chat(body)
            except EndpointError as exc:
                rec('endpoint_error', status=exc.status, transient=exc.transient,
                    message=str(exc)[:500], attempt=attempt)
                if exc.status == 400 and 'context' in str(exc).lower() and attempt == 0:
                    _compact(messages, 2)
                    body = request_body(messages, budget, sampling, budget.thinking_budget)
                    attempt += 1
                    continue
                if not exc.transient or attempt >= max_retries:
                    if exc.status == 400:
                        reason = 'context_overflow'
                    elif exc.status in (401, 403, 404):
                        reason = 'config_error'   # wrong endpoint/model/key: never retried
                    else:
                        reason = 'infra_error'
                    break
                sleep(min(60.0, 2.0 * 2 ** attempt))
                attempt += 1
        if reason:
            break
        turns += 1
        choice = resp['choices'][0]
        msg = choice['message']
        finish = (choice.get('finish_reason') or '').lower()
        usage = resp.get('usage') or {}
        last_prompt_tokens = usage.get('prompt_tokens', last_prompt_tokens)
        usage_total['prompt_tokens'] += usage.get('prompt_tokens', 0)
        usage_total['completion_tokens'] += usage.get('completion_tokens', 0)
        details = usage.get('completion_tokens_details') or {}
        usage_total['reasoning_tokens'] += details.get('reasoning_tokens') or 0
        reasoning = msg.get('reasoning_content') or msg.get('reasoning')
        tool_calls = msg.get('tool_calls') or []
        rec('model', turn=turns, finish_reason=finish, usage=usage, content=msg.get('content'),
            reasoning=reasoning, tool_calls=tool_calls)

        assistant = {'role': 'assistant', 'content': msg.get('content') or ''}
        if tool_calls:
            assistant['tool_calls'] = tool_calls
        if reasoning and sampling.get('carry_reasoning', False):
            assistant['reasoning_content'] = reasoning   # decided in the smoke test (WP1)
        messages.append(assistant)

        if tool_calls:
            nudges = 0
            for tc in tool_calls:
                fn = tc.get('function', {})
                out = box.dispatch(fn.get('name', ''), fn.get('arguments', '{}'))
                rec('tool', turn=turns, id=tc.get('id'), name=fn.get('name'),
                    arguments=fn.get('arguments'), result=out)
                messages.append({'role': 'tool', 'tool_call_id': tc.get('id', ''),
                                 'content': out})
            if box.patch_submitted:
                reason = 'submitted'
            elif box.calls_remaining() <= 0 or box.time_remaining() <= 0:
                reason = 'tool_budget' if box.calls_remaining() <= 0 else 'time_budget'
            continue

        nudges += 1
        if nudges > C.MAX_NUDGES:
            reason = 'nudges_exhausted'
            break
        text = msg.get('content') or ''
        if '<|tool_call>' in text and '<tool_call|>' not in text:
            nudge = NUDGE_UNCLOSED
        elif 'length' in finish or 'max_tokens' in finish:
            nudge = NUDGE_LENGTH
        else:
            nudge = NUDGE_STOP
        rec('nudge', turn=turns, count=nudges, text=nudge)
        messages.append({'role': 'user', 'content': nudge})

    patch = box.submitted_patch if box.patch_submitted else workspace.diff()
    summary = {'termination': reason, 'patch_submitted': box.patch_submitted,
               'patch': patch, 'turns': turns, 'tool_calls_used': box.tool_calls_used,
               'elapsed_seconds': round(box.elapsed(), 3),
               'budget_exhausted': reason in ('tool_budget', 'time_budget', 'turn_budget',
                                              'context_overflow'),
               'usage': usage_total, 'graph_builds': box.graph.builds}
    rec('end', **{k: v for k, v in summary.items() if k != 'patch'},
        patch_sha256=hashlib.sha256(patch.encode()).hexdigest())
    rec.close()
    return summary
