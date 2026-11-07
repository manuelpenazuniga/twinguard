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

# File access on the agent's behalf runs AS THE AGENT UID when run_as is set, so a symlink
# (or a file swapped for one between check and use) can never make the controller read or
# write anything the agent itself could not (Astra pre-pilot review 2026-11-07).
_FS_HELPER = r'''
import json, os, stat, sys
op, p = sys.argv[1], sys.argv[2]
if op == 'stat':
    try:
        m = os.stat(p).st_mode
        print('file' if stat.S_ISREG(m) else 'dir' if stat.S_ISDIR(m) else 'other')
    except OSError:
        print('none')
elif op == 'read':
    with open(p, 'rb') as f:
        sys.stdout.buffer.write(f.read())
elif op == 'write':
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    data = sys.stdin.buffer.read()
    with open(p, 'wb') as f:
        f.write(data)
elif op == 'dump_py':
    out = {}
    for dp, dns, fns in os.walk(p):
        dns[:] = sorted(d for d in dns if not d.startswith('.')
                        and not os.path.islink(os.path.join(dp, d)))
        for fn in sorted(fns):
            full = os.path.join(dp, fn)
            if not fn.endswith('.py') or os.path.islink(full):
                continue
            try:
                if not stat.S_ISREG(os.lstat(full).st_mode):
                    continue
                with open(full, 'rb') as f:
                    out[os.path.relpath(full, p)] = f.read().decode('utf-8', 'replace')
            except OSError:
                continue
    sys.stdout.write(json.dumps(out))
'''


class WorkspaceError(Exception):
    def __init__(self, error_type, message):
        super().__init__(message)
        self.error_type = error_type


class Workspace:
    def __init__(self, root, tmp, python_bin=None, run_as=None):
        self.root = Path(root).resolve()
        # Unprivileged uid for every agent-triggered process (bash, git, tests). The runner
        # creates the user, chowns root/tmp to it and keeps oracles/logs in 0700 controller
        # directories (docs/decisions.md D3, Kaggle probe 2026-11-06). None = development.
        self.run_as = run_as
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

    def prefix(self):
        if not self.run_as:
            return []
        return ['setpriv', f'--reuid={self.run_as}', f'--regid={self.run_as}', '--clear-groups',
                '--no-new-privs', '--']

    def kill_user_processes(self):
        """Terminate every process of the agent uid (nothing may survive the run)."""
        if self.run_as:
            subprocess.run(['pkill', '-KILL', '-u', str(self.run_as)], capture_output=True)

    # ------------------------------------------------------------ file access
    def _fs(self, op, path, data=None):
        r = subprocess.run([*self.prefix(), sys.executable, '-I', '-S', '-c', _FS_HELPER, op,
                            str(path)], cwd=self.root, env=self.env(), input=data,
                           capture_output=True, timeout=60)
        if r.returncode != 0:
            msg = r.stderr.decode('utf-8', 'replace').strip().splitlines()[-1:] or ['']
            raise OSError(msg[0])
        return r.stdout

    def kind(self, full):
        """'file' | 'dir' | 'other' | 'none' as seen by the agent uid."""
        if not self.run_as:
            full = Path(full)
            return 'file' if full.is_file() else 'dir' if full.is_dir() else \
                ('other' if full.exists() else 'none')
        return self._fs('stat', full).decode().strip()

    def read_text(self, full):
        if not self.run_as:
            return Path(full).read_text(encoding='utf-8', errors='replace')
        return self._fs('read', full).decode('utf-8', errors='replace')

    def write_text(self, full, text):
        if not self.run_as:
            Path(full).parent.mkdir(parents=True, exist_ok=True)
            Path(full).write_text(text, encoding='utf-8')
            return
        self._fs('write', full, text.encode('utf-8'))

    def py_sources(self):
        """{relative path: text} of regular, non-symlinked *.py files outside hidden dirs."""
        if not self.run_as:
            return None
        import json
        return json.loads(self._fs('dump_py', self.root))

    def rewrite(self, command):
        command = _WS_RE.sub(str(self.root), command)
        return _TMP_RE.sub(str(self.tmp), command)

    def run(self, command, timeout):
        """Return dict(stdout, stderr, exit_code, timed_out)."""
        proc = subprocess.Popen([*self.prefix(), '/bin/bash', '-c', self.rewrite(command)],
                                cwd=self.root,
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
        r = subprocess.run([*self.prefix(), 'git', *args], cwd=self.root, env=self.env(),
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
