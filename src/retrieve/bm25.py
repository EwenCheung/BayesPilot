"""BM25 (Okapi, Lucene-style IDF) as an evidence term — the one lexical route never tried here.

**Why this is worth measuring again.** An IDF-weighted overlap route over this exact surface was
measured *harmful*, monotonically (D23) — but it read that surface through `attributes.tokens()`,
which destroys 11.1% of `%` tokens, drops 24.7% of short tokens, and collapses term frequency to 1.
The negative was measured on a damaged surface. BM25 over the repaired one adds two things the old
route could not express even in principle:

* **term saturation** — the 5th occurrence of "cotton" says little more than the 2nd, via `k1`;
* **length normalisation** — a 300-word description should not beat a 6-word title on term count, via `b`.

So this isolates precisely what BM25 adds over a route we have already priced at below zero. Same
surface (`index.lexical_text`), same query construction, same bounded-gain plumbing — one variable.

    idf(t)   = log(1 + (N - df + 0.5) / (df + 0.5))                      Lucene's non-negative form
    score    = Σ_{t∈q} idf(t) · f(t,d)·(k1+1) / (f(t,d) + k1·(1 - b + b·|d|/avgdl))
    strength = clip(score / Σ_{t∈q} idf(t), 0, 1)

The normaliser is the score of a document of average length containing each query term exactly once —
at `f = 1` and `|d| = avgdl` the saturation factor is exactly 1, so that document scores `Σ idf(t)`.
That keeps `strength` in the same [0, 1] units as every other evidence term, so `bm25_gain` means what
`soft_card_gain` means.

⚠️ `bm25_gain` defaults to **0.0** until the sweep in `scripts/fit_bm25.py` confirms it on
`data/train.jsonl` and it holds out on `dev`. A route that has never earned a held-out number does not
ship on the strength of a plausible mechanism.
"""
from __future__ import annotations

import math

from src.understand.tokens import terms

K1 = 1.5
B = 0.75


class Bm25Route:
    """Okapi BM25 over the catalog's lexical surface. Built once, cached on the index."""

    def __init__(self, index, k1: float = K1, b: float = B) -> None:
        self.k1, self.b = k1, b
        self.freqs: dict[str, dict[str, int]] = {}
        self.length: dict[str, int] = {}
        df: dict[str, int] = {}
        for asin, text in index.lexical_text.items():
            counts: dict[str, int] = {}
            counted = terms(text)
            for term in counted:
                counts[term] = counts.get(term, 0) + 1
            self.freqs[asin] = counts
            self.length[asin] = len(counted) or 1
            for term in counts:
                df[term] = df.get(term, 0) + 1
        n = len(self.freqs) or 1
        self.avgdl = sum(self.length.values()) / n
        self.idf = {t: math.log(1.0 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str, candidates: list[str]) -> dict[str, float]:
        wanted = list(dict.fromkeys(terms(query)))   # unique, order-stable
        if not wanted:
            return {}
        ceiling = sum(self.idf.get(t, 0.0) for t in wanted)
        if ceiling <= 0:
            return {}
        out: dict[str, float] = {}
        for asin in candidates:
            counts = self.freqs.get(asin)
            if not counts:
                continue
            norm = self.k1 * (1.0 - self.b + self.b * self.length[asin] / self.avgdl)
            total = 0.0
            for term in wanted:
                f = counts.get(term, 0)
                if f:
                    total += self.idf.get(term, 0.0) * f * (self.k1 + 1.0) / (f + norm)
            if total > 0:
                out[asin] = min(1.0, total / ceiling)
        return out


def bm25_scores(index, query: str, candidates: list[str], flags) -> dict[str, float]:
    """Lazily build the route on first use and cache it on the index."""
    route = getattr(index, "_bm25", None)
    if route is None:
        route = index._bm25 = Bm25Route(index,
                                        k1=getattr(flags, "bm25_k1", K1),
                                        b=getattr(flags, "bm25_b", B))
    return route.scores(query, candidates)
