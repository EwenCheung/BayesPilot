"""Inline `demo/traces.js` into `demo/index.html` so the page is a single self-contained file.

    python3 demo/capture.py && python3 demo/build.py
"""
from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = HERE.joinpath("traces.js").read_text()
page = HERE.joinpath("template.html").read_text()
out = page.replace("/*__TRACES__*/", data.strip())
HERE.joinpath("index.html").write_text(out)
print(f"demo/index.html  {len(out)/1024:.0f} KB  (self-contained, open by double-click)")
