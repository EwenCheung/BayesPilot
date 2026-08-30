"""BM25 (Okapi, Lucene-style IDF) as an evidence term — the one lexical route never tried here.

**Why this is worth one measurement and not a rebuild.** `src/r3/lexical.py` already scores IDF-weighted
overlap over this exact surface and was measured *harmful*, monotonically (D23). BM25 is that route
plus two things it lacks:

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
`idf_gain` and `semantic_gain` mean.

⚠️ Defaults to **off**. Nothing about R1–R4 changes: `SelectiveBelief` reads the gain with `getattr`,
and R4's flags have no such field.
"""
from __future__ import annotations

import math

from src.common.attributes import tokens

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
            terms = [t for t in tokens(text)]
            for term in terms:
                counts[term] = counts.get(term, 0) + 1
            self.freqs[asin] = counts
            self.length[asin] = len(terms) or 1
            for term in counts:
                df[term] = df.get(term, 0) + 1
        n = len(self.freqs) or 1
        self.avgdl = sum(self.length.values()) / n
        self.idf = {t: math.log(1.0 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str, candidates: list[str]) -> dict[str, float]:
        wanted = tokens(query)
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
