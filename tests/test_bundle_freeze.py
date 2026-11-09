"""DEV-1 regression: the kernel bundle that notebooks/build_kernel.py archives from the frozen
commit must contain every file the frozen kernel's verify_freeze checks (its BUNDLED prefixes
over the manifest's file lists), with the frozen hashes and nothing extra."""
import ast
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FROZEN = 'b24a4dd'


def git(*a, text=False):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, check=True, text=text).stdout


def test_bundle_from_the_frozen_commit_passes_verify_freeze():
    try:
        git('cat-file', '-e', f'{FROZEN}^{{commit}}')
    except subprocess.CalledProcessError:
        pytest.skip('frozen commit not in this clone')
    src = (ROOT / 'notebooks' / 'build_kernel.py').read_text()
    paths = ast.literal_eval(re.search(r'PATHS = (\[.*?\])', src, re.S).group(1))
    kernel = git('show', f'{FROZEN}:notebooks/pilot_l4/pilot_l4.py', text=True)
    bundled = ast.literal_eval(re.search(r'BUNDLED = (\(.*?\))\n', kernel, re.S).group(1))
    tf = tarfile.open(fileobj=io.BytesIO(git('archive', '--format=tar', FROZEN, '--', *paths)))
    files = {m.name: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}
    m = json.loads(files['freeze/manifest.json'])
    frozen = {}
    for v in m['files'].values():
        frozen.update(v)
    for t in m['templates'].values():
        frozen.update(t['files'])
    checked = {p: h for p, h in frozen.items() if p.startswith(bundled)}
    assert checked
    assert [p for p in checked if p not in files] == []
    assert [p for p, h in checked.items() if hashlib.sha256(files[p]).hexdigest() != h] == []
    assert [p for p in files if p.startswith(bundled) and p not in frozen] == []
