import sys
from pathlib import Path

ROOT = Path(__file__).parent
KIT = ROOT / "techjam-conversational-search-main"
for path in (ROOT, KIT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
