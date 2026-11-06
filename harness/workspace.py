"""Sandboxed workspace (replica of the official subprocess backend, README 4.1).

The agent sees /workspace and /tmp; commands are rewritten to the per-run directories
and run with `bash -c` in a new process group, killed as a group on timeout. The
environment is scrubbed (no tokens or keys reach the agent). Network isolation is the
platform's job: Kaggle L4x4 has no internet. Oracles and logs live OUTSIDE this tree.
"""
import os
import re
import signal
import subprocess
import sys
from pathlib import Path, PurePosixPath

from harness import contract as C

_WS_RE = re.compile(r'(?<![\w./-])/workspace(?=/|\b|$)')
_TMP_RE = re.compile(r'(?<![\w./-])/tmp(?=/|\b|$)')
SAFE_ENV_KEYS = ('PATH', 'LANG', 'LC_ALL', 'TZ')


class WorkspaceError(Exception):
    def __init__(self, error_type, message):
        super().__init__(message)
        self.error_type = error_type


class Workspace:
    def __init__(self, root, tmp, python_bin=None):
        self.root = Path(root).resolve()
        # `python`/`pytest` on PATH come from the harness interpreter's bin directory,
        # as in the official python image (README 4.1).
        self.python_bin = str(Path(python_bin or sys.executable).parent)
        self.tmp = Path(tmp).resolve()
        self.tmp.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ paths
    def resolve(self, filepath):
        """README 6.2: strip leading '/workspace/' or '/', reject '..'."""
        p = str(filepath).strip()
        if p.startswith('/workspace/'):
            p = p[len('/workspace/'):]
        elif p == '/workspace':
            p = ''
        p = p.lstrip('/')
        if '..' in PurePosixPath(p).parts:
            raise WorkspaceError(C.ValidationError, f'path traversal is not allowed: {filepath}')
        full = (self.root / p).resolve()
        if full != self.root and self.root not in full.parents:
            raise WorkspaceError(C.ValidationError, f'path escapes the workspace: {filepath}')
        return full

    def rel(self, full):
        return full.relative_to(self.root).as_posix()

    # ------------------------------------------------------------ commands
    def env(self):
        env = {k: os.environ[k] for k in SAFE_ENV_KEYS if k in os.environ}
        env['PATH'] = self.python_bin + os.pathsep + env.get('PATH', '/usr/bin:/bin')
        env.update(HOME=str(self.tmp), TMPDIR=str(self.tmp), TEST_TMPDIR=str(self.tmp),
                   GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_NAME='Agent',
                   GIT_AUTHOR_EMAIL='agent@eval', GIT_COMMITTER_NAME='Agent',
                   GIT_COMMITTER_EMAIL='agent@eval')
        return env

    def rewrite(self, command):
        command = _WS_RE.sub(str(self.root), command)
        return _TMP_RE.sub(str(self.tmp), command)

    def run(self, command, timeout):
        """Return dict(stdout, stderr, exit_code, timed_out)."""
        proc = subprocess.Popen(['/bin/bash', '-c', self.rewrite(command)], cwd=self.root,
                                env=self.env(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
        try:
            out, err = proc.communicate(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = proc.communicate()
            timed_out = True
        dec = lambda b: b.decode('utf-8', errors='replace')
        return dict(stdout=dec(out), stderr=dec(err), exit_code=proc.returncode,
                    timed_out=timed_out)

    def git(self, *args, check=True):
        r = subprocess.run(['git', *args], cwd=self.root, env=self.env(),
                           capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f'git {args} failed: {r.stderr}')
        return r.stdout

    # ------------------------------------------------------------ baseline / patch
    def init_baseline(self):
        """README 4.2 steps 3 and 7 (git exclude, baseline commit)."""
        if not (self.root / '.git').exists():
            self.git('init', '-q', '-b', 'main')
        excl = self.root / '.git' / 'info' / 'exclude'
        excl.parent.mkdir(parents=True, exist_ok=True)
        excl.write_text('\n'.join(C.GIT_EXCLUDE) + '\n', encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'baseline', '--allow-empty')

    def diff(self):
        """README 8.1: git add -N . && git diff --binary HEAD, protected files stripped."""
        self.git('add', '-N', '.')
        return strip_protected_files_from_patch(self.git('diff', '--binary', 'HEAD'))


def is_protected(path):
    p = PurePosixPath(path)
    if p.name in C.PROTECTED_CONFIG or p.suffix == '.pth':
        return True
    if p.suffix == '.py' and (p.name.startswith('test_') or p.name.endswith('_test.py')
                              or any(part in C.PROTECTED_TEST_DIRS for part in p.parts[:-1])):
        return True
    return False


def strip_protected_files_from_patch(patch):
    if not patch:
        return patch
    sections = re.split(r'(?m)^(?=diff --git )', patch)
    keep = []
    for s in sections:
        m = re.match(r'diff --git a/(\S+) b/(\S+)', s)
        if m and (is_protected(m.group(1)) or is_protected(m.group(2))):
            continue
        keep.append(s)
    return ''.join(keep)


def files_changed(patch):
    return len(re.findall(r'(?m)^diff --git ', patch))
