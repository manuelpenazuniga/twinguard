"""Write notebooks/colab/twinguard_colab.ipynb: the bootstrap (colab_bootstrap.py) embedded in
one cell, a config cell, and the run cell. Upload the notebook and the built kernel script
(`python notebooks/build_kernel.py notebooks/pilot_l4 --define PLATFORM=colab --define
MODE=runner_smoke --out-dir <dir>`) to Drive; Colab secrets KAGGLE_USERNAME and KAGGLE_KEY.

  python notebooks/colab/make_notebook.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def cell(kind, src):
    c = {'cell_type': kind, 'metadata': {}, 'source': src}
    if kind == 'code':
        c.update(execution_count=None, outputs=[])
    return c


def main():
    boot = (HERE / 'colab_bootstrap.py').read_text()
    cells = [
        cell('markdown', '# TwinGuard on Colab (D13 x2 only)\n\nRuntime: **A100** (40 or 80 GB). '
             'Secrets (key icon): `KAGGLE_USERNAME`, `KAGGLE_KEY` with notebook access. '
             'Put the built kernel script in Drive and set `SCRIPT` below; keep this tab open '
             'while it runs (outputs are copied to `RUN_DIR` every 5 min).'),
        cell('code', "RUN_NAME = 'colab_smoke_1'\n"
                     "SCRIPT = '/root/drive/MyDrive/Colab Notebooks/pilot_l4_colab_smoke.py'\n"
                     "RESUME = None   # Drive path of a previous results_sealed.tar.gz; needs a script rebuilt with RESUME_SHA256\n"
                     "RUN_DIR = f'/root/drive/MyDrive/Colab Notebooks/twinguard_runs/{RUN_NAME}'"),
        cell('code', boot),
        cell('code', "from google.colab import drive, userdata\n"
                     "drive.mount('/root/drive')\n"
                     "print('gpu', gpu())\n"
                     "print('python', venv())\n"
                     "print('downloads', downloads(userdata.get('KAGGLE_USERNAME'), userdata.get('KAGGLE_KEY')))\n"
                     "print('script sha256', place(SCRIPT, RESUME))\n"
                     "rc = run(RUN_DIR)"),
    ]
    nb = {'cells': cells, 'metadata': {'accelerator': 'GPU', 'colab': {'gpuType': 'A100'},
                                       'kernelspec': {'name': 'python3', 'display_name': 'Python 3'}},
          'nbformat': 4, 'nbformat_minor': 5}
    (HERE / 'twinguard_colab.ipynb').write_text(json.dumps(nb, indent=1) + '\n')


if __name__ == '__main__':
    main()
