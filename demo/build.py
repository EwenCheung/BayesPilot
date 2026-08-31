"""Inline `demo/traces.js` into `demo/index.html` so the page is one self-contained file.

    python3 demo/build.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
page = HERE.joinpath("template.html").read_text()
data = HERE.joinpath("traces.js").read_text().strip()
HERE.joinpath("index.html").write_text(page.replace("/*__TRACES__*/", data))
print(f"demo/index.html  {HERE.joinpath('index.html').stat().st_size/1024:.0f} KB")
