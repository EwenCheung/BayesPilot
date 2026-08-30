"""Global candidate rescue routes and fusion — the green nodes in the build plan.

Three recall-oriented global retrievers that search the FULL catalog, not just the category pool:
  RAWSEM   — semantic rescue from the original customer text
  NORMSEM  — semantic rescue from the LLM-normalized text (requires router)
  RAWLEX   — IDF/BM25-style lexical rescue from the original text

One union rule:
  UNION    — candidate union (never intersection) across all retrieval routes

One fusion method:
  RRF      — reciprocal-rank fusion baseline across multiple ranked lists

⚠️ These are candidate GENERATORS, not in-pool re-scorers. The existing `semantic.py` and
`lexical.py` score candidates already in the pool; these retrieve candidates the pool missed.
"""
from __future__ import annotations

import math
from collections import defaultdict

from src.common.attributes import tokens


class GlobalLexicalRescue:
    """BM25-style global lexical rescue over the full 50K catalog.

    Builds an inverted index at startup. Given a query, returns the top-K ASINs
    globally by IDF-weighted token overlap — rescuing products the category
    posterior missed because of vocabulary mismatch.
    """

    def __init__(self, index, cap: int = 64) -> None:
        self.index = index
        # Build inverted index: token → set of ASINs containing it
        self._postings: dict[str, set[str]] = defaultdict(set)
        self._doc_tokens: dict[str, frozenset[str]] = {}
        df: dict[str, int] = {}

        for asin, text in index.lexical_text.items():
            got = tokens(text)
            # Keep the cap-rarest tokens per doc, deterministically sorted
            for token in got:
                df[token] = df.get(token, 0) + 1

        n = len(index.lexical_text) or 1
        self.idf = {t: math.log(1.0 + n / (1.0 + c)) for t, c in df.items()}

        for asin, text in index.lexical_text.items():
            got = tokens(text)
            kept = frozenset(sorted(got, key=lambda t: (-self.idf.get(t, 0), t))[:cap])
            self._doc_tokens[asin] = kept
            for token in kept:
                self._postings[token].add(asin)

    def rescue(self, query: str, top_k: int = 200, exclude: set[str] | None = None) -> list[tuple[str, float]]:
        """Return up to top_k (asin, score) pairs from the FULL catalog, excluding `exclude`."""
        wanted = tokens(query)
        if not wanted:
            return []
        # Gather candidate ASINs that share at least one token with the query
        candidate_asins: set[str] = set()
        for token in wanted:
            candidate_asins |= self._postings.get(token, set())
        if exclude:
            candidate_asins -= exclude

        ceiling = sum(self.idf.get(t, 0.0) for t in wanted) or 1.0
        scored: list[tuple[str, float]] = []
        for asin in candidate_asins:
            hit = wanted & self._doc_tokens.get(asin, frozenset())
            if hit:
                score = sum(self.idf.get(t, 0.0) for t in hit) / ceiling
                scored.append((asin, score))

        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]


class GlobalSemanticRescue:
    """Global semantic rescue using precomputed embeddings over the full catalog.

    Uses the same embedding backends as the existing semantic.py (SVD or BLaIR),
    but performs a GLOBAL top-K search across all 50K products rather than
    scoring only within the category pool.

    Falls back gracefully when no embeddings are available.
    """

    def __init__(self, semantics) -> None:
        """Takes an existing SvdSemantics or BlairSemantics instance."""
        self.semantics = semantics
        self._all_asins = list(semantics.asins) if semantics else []

    def rescue(
        self, query: str, top_k: int = 200, exclude: set[str] | None = None
    ) -> list[tuple[str, float]]:
        """Return up to top_k (asin, score) pairs from the FULL catalog."""
        if not self.semantics or not query.strip():
            return []
        # Encode the query
        vector = self.semantics.encode(query)
        import numpy as np
        if not np.any(vector):
            return []

        # Score ALL products globally
        rows = [self.semantics._row[a] for a in self._all_asins if a in self.semantics._row]
        if not rows:
            return []
        sims = self.semantics._vectors[rows] @ vector
        # Pair with ASINs and sort
        pairs = [
            (self._all_asins[r], float(max(0.0, s)))
            for r, s in zip(rows, sims)
        ]
        if exclude:
            pairs = [(a, s) for a, s in pairs if a not in exclude]
        pairs.sort(key=lambda x: -x[1])
        return pairs[:top_k]


def candidate_union(
    category_pool: list[str],
    rescue_results: list[list[tuple[str, float]]],
) -> list[str]:
    """Union of category pool ASINs and all rescue results. Never intersection.

    C = C_category ∪ C_rescue_1 ∪ C_rescue_2 ∪ ...
    """
    seen: set[str] = set()
    union: list[str] = []
    # Category pool first (preserves ordering priority)
    for asin in category_pool:
        if asin not in seen:
            seen.add(asin)
            union.append(asin)
    # Then rescue candidates
    for results in rescue_results:
        for asin, _score in results:
            if asin not in seen:
                seen.add(asin)
                union.append(asin)
    return union


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[str]],
    weights: dict[str, float] | None = None,
    k: int = 60,
) -> list[str]:
    """Reciprocal-Rank Fusion across multiple named ranked lists.

    RRF(i) = Σ_r  w_r / (k + rank_r(i))

    Each route contributes independently. A candidate absent from a route
    simply gets no contribution from that route (never penalized).

    Args:
        ranked_lists: {route_name: [asin, asin, ...]} ordered best-first.
        weights: optional per-route weights; defaults to 1.0 for each.
        k: the RRF constant (standard default = 60).

    Returns:
        ASINs sorted by descending RRF score.
    """
    if weights is None:
        weights = {name: 1.0 for name in ranked_lists}

    scores: dict[str, float] = defaultdict(float)
    for name, ranked in ranked_lists.items():
        w = weights.get(name, 1.0)
        if w <= 0:
            continue
        for rank, asin in enumerate(ranked, start=1):
            scores[asin] += w / (k + rank)

    return sorted(scores, key=lambda a: -scores[a])
