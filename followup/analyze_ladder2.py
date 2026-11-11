"""D17b (ladder2): the single analysis of the D17b blocks (Gemma 4 E2B and 26B-A4B), with D17's
analysis (followup/analyze_ladder.py, imported unchanged) on D17b's seal. Run ONCE (O_EXCL claim
by the D17b seal hash).

  python followup/analyze_ladder2.py --results DIR/results --x3-results X3/results --out results/ladder2
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from followup import analyze_ladder as L  # noqa: E402  (sealed in D17; imported, never changed)

L.MANIFEST = ROOT / 'followup' / 'ladder2_manifest.json'

if __name__ == '__main__':
    L.main()
