"""Build the demo page, in two forms.

    python3 demo/capture.py && python3 demo/build.py

* `demo/index.html`    — a complete, standalone HTML document. Double-click it; it opens in any
                         browser, offline, with no server and no install.
* `demo/artifact.html` — the same page WITHOUT `<!doctype>/<html>/<head>/<body>`, which is what the
                         artifact host expects because it supplies that skeleton itself. Publishing
                         the standalone file instead would nest one document inside another.

Both are generated from `template.html` + `traces.js`, so they can never drift apart.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
body = HERE.joinpath("template.html").read_text().replace(
    "/*__TRACES__*/", HERE.joinpath("traces.js").read_text().strip())

HERE.joinpath("artifact.html").write_text(body)

# The host normally provides these three: a charset, a viewport, and a light reset. A file opened
# from disk gets none of them, so the standalone build carries its own.
standalone = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html {{ color-scheme: light dark; }}
  body {{ margin: 0; }}
  img {{ max-width: 100%; }}
  [hidden] {{ display: none !important; }}
</style>
{body}
</body>
</html>
"""
# `template.html` opens with <title> and its own <style>, both legal in <head>; the first element
# after them starts the body, so the split point is the first <div class="wrap">.
head_end = standalone.index('<div class="wrap">')
standalone = standalone[:head_end] + "</head>\n<body>\n" + standalone[head_end:]
HERE.joinpath("index.html").write_text(standalone)

for name in ("index.html", "artifact.html"):
    print(f"demo/{name:<14} {HERE.joinpath(name).stat().st_size / 1024:>5.0f} KB")
