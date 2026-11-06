"""Frozen contract of the TwinGuard harness (protocol 7.1, P2).

The harness is API-compatible with the official competition harness (`swegemma` /
`adk-eval-core`), replicated from the competition's HARNESS_README.md (sections 5-7)
because neither package is distributed. It is NOT equivalent to the official harness.
Everything that defines tool behaviour lives here so it can be hashed and frozen
before the pilot: limits, error types, serialization, budgets and prompt text.

Nothing in this module (or anywhere in harness/) may depend on the framing (N/P/A).
tests/test_harness_contract.py checks that.
"""
import hashlib
import json
from dataclasses import asdict, dataclass

HARNESS_VERSION = '0.1'

# HarnessLimits (README 7.1). Identical for every run.
MAX_STDOUT_CHARS = 5000        # run_command stdout/stderr, edit diff, graph outputs
MAX_FILE_LINES = 150           # read_file
MAX_FILE_CHARS = 10000         # read_file
COMMAND_TIMEOUT_SECONDS = 300  # single run_command
MIN_COMMAND_TIMEOUT = 5        # min(timeout, max(5, remaining_time))
BUDGET_WARNING_MIN_TOTAL = 20  # warn when budget.tool_calls >= 20 ...
BUDGET_WARNING_REMAINING = 10  # ... and remaining <= 10
MAX_NUDGES = 3

# Files the official patch extraction strips (README 8.1).
PROTECTED_CONFIG = {'conftest.py', 'pytest.ini', 'pyproject.toml', 'tox.ini', 'setup.cfg',
                    '.pytest.ini', 'sitecustomize.py', 'usercustomize.py', '_swegemma_stubs.py'}
PROTECTED_TEST_DIRS = ('tests', 'test', 'testing')
GIT_EXCLUDE = ['__pycache__/', '*.pyc', '.pytest_cache/', '*.egg-info/', 'build/', 'dist/',
               '.coverage']

# Error types emitted by tools (README 6). BudgetExhausted is ours: the README does not
# document what a gated tool returns once the budget is spent.
CommandError = 'CommandError'
TimeoutExceeded = 'TimeoutExceeded'
FileEditError = 'FileEditError'
ValidationError = 'ValidationError'
FileNotFound = 'FileNotFoundError'
NodeNotFound = 'NodeNotFound'
GraphUnavailable = 'GraphUnavailable'
BudgetExhausted = 'BudgetExhausted'


@dataclass(frozen=True)
class Budget:
    """Per-run budget, identical across arms; values are calibrated in the pilot
    with framing-blind criteria (protocol 7.1) and then frozen."""
    tool_calls: int = 100              # inference.py default
    time_minutes: float = 60.0
    turns: int = 500
    context_tokens: int = 32768
    max_output_tokens: int = 16384     # GenerationConstraints default
    thinking_budget: int = 4096        # >= 4096 with reasoning on (protocol 7.1)
    compaction_threshold: int = 14336  # EventsCompactionConfig.token_threshold
    compaction_retention: int = 5      # EventsCompactionConfig.event_retention_size

    def as_dict(self):
        return asdict(self)


def dumps(obj):
    """Single serialization for every tool response (frozen)."""
    return json.dumps(obj)


def ok(**fields):
    return dumps({'status': 'ok', **fields})


def error(error_type, message, **details):
    out = {'status': 'error', 'error_type': error_type, 'error_message': message}
    if details:
        out['details'] = details
    return out


def plugin_error(exc_name, message):
    """ToolErrorPlugin format for unknown tools or bad arguments (README 5.3).
    Note the key is 'error', not 'error_message', as documented."""
    return dumps({'status': 'error', 'error_type': exc_name, 'error': message})


def truncate(text, limit=MAX_STDOUT_CHARS):
    return (text, False) if len(text) <= limit else (text[:limit], True)


def contract_hash():
    """Hash of the harness source files, frozen with the preregistration (WP9)."""
    from pathlib import Path
    here = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for p in sorted(here.glob('*.py')):
        h.update(p.name.encode() + b'\0' + p.read_bytes() + b'\0')
    return h.hexdigest()
