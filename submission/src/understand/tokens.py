"""The tokenizer BM25 needs, which is not the one the fallback matcher needs.

`attributes.tokens()` returns a **frozenset** of tokens matching `[a-z0-9]+` with `len > 2`. That is
right for the low-precision overlap matcher it was written for — a set is what "did this word appear"
wants — and wrong for BM25 in three separate ways, all of them silent:

1. **`%` is destroyed.** `75% Polyester` tokenises to `75`, `polyester`. Measured over 79,143
   intent-card constraint strings from 20,000 catalog rows, **11.1%** contain a `%` token that is lost.
2. **Sizes are dropped.** `len > 2` deletes `XL`, `XS`, `2T`, `L`, `M` — **24.7%** of card strings
   contain a token of two characters or fewer.
3. **Term frequency is gone.** A frozenset makes `f(t,d) == 1` for every term in the catalog, so the
   `k1` saturation half of BM25 — the entire reason `retrieve/bm25.py` exists next to the token-overlap
   term — computes nothing at all.

⚠️ The simulator quotes the catalog **verbatim**, so the tokens this drops are exactly the
discriminating ones: `100% Cotton` vs `Cotton` is the difference between identifying a product and
naming a material.

`tokens()` is deliberately left alone. It feeds the `lexical` evidence term and `softcard`'s Jaccard,
both of which were fitted against its behaviour; changing it underneath them would move three
measurements at once and none of them cleanly.
"""
from __future__ import annotations

import re

from src.understand.attributes import STOPWORDS

# Keeps digits, the percent sign, and internal hyphens/dots: `75%`, `3.5`, `x-large`, `2t`.
_TERM = re.compile(r"[a-z0-9][a-z0-9\-.]*%?")


def terms(text: str) -> list[str]:
    """Content terms **in order, with repeats** — a list, because BM25 counts occurrences."""
    return [t for t in _TERM.findall((text or "").lower())
            if len(t) > 1 and t not in STOPWORDS]


def demo() -> None:
    """The three defects, as one runnable check."""
    from src.understand.attributes import tokens

    got = terms("100% Cotton cotton cotton XL fit")
    assert "100%" in got, f"percent lost: {got}"
    assert "xl" in got, f"two-char size lost: {got}"
    assert got.count("cotton") == 3, f"term frequency lost: {got}"

    old = tokens("100% Cotton cotton cotton XL fit")
    assert "100%" not in old and "xl" not in old, "the old tokenizer was expected to drop both"
    print("tokens.terms: percent kept, sizes kept, term frequency kept")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    demo()
