"""TwinGuard agent harness (WP2). API-compatible with the official competition harness."""
import sys
from pathlib import Path

_TG = str(Path(__file__).resolve().parent.parent / 'twinguard')
if _TG not in sys.path:
    sys.path.insert(0, _TG)
