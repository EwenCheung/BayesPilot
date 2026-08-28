"""Spec 3.2 — the read-only catalog index.

Built once in `Agent.__init__` and shared by every session (IMPORTANT.md §2), so build cost
amortises to zero. Everything text-heavy is computed **per category pool, lazily, and cached**:
a session only ever looks inside one coarse category, and 1,115 categories at 50,000 products
is far more work than any run needs.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from src.common.attributes import normalise, tokens
from src.common.simulator import _flatten_values, coarse_category, intent_card


class PoolFeatures:
    """Per-product matchable surfaces for one coarse category."""

    __slots__ = ("asins", "phrases", "pairs", "tokens")

    def __init__(self, asins: list[str]) -> None:
        self.asins = asins
        self.phrases: dict[str, frozenset[str]] = {}   # asin -> its exact card strings
        self.pairs: dict[str, frozenset[tuple[str, str]]] = {}
        self.tokens: dict[str, frozenset[str]] = {}


class CatalogIndex:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.popularity: dict[str, float] = {}
        self.rating_number: dict[str, int] = {}
        self.category: dict[str, str] = {}
        self.by_category: dict[str, list[str]] = {}
        self.card_strings: dict[str, tuple[str, ...]] = {}   # in the simulator's own order
        self.spec_strings: dict[str, list[str]] = {}   # flattened features+details, the simulator's source
        self.title: dict[str, str] = {}
        self._pools: dict[str, PoolFeatures] = {}

        with Path(catalog_path).open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                asin = str(product["parent_asin"])
                card = intent_card(product)
                self.card_strings[asin] = tuple(
                    dict.fromkeys([*card["hard_constraints"], *card["soft_preferences"]])
                )
                self.spec_strings[asin] = [
                    *_flatten_values(product.get("features")),
                    *_flatten_values(product.get("details")),
                ]
                self.title[asin] = str(product.get("title") or "")
                reviews = int(product.get("rating_number") or 0)
                self.rating_number[asin] = reviews
                self.popularity[asin] = math.log1p(reviews)
                category = coarse_category([str(v) for v in product.get("categories") or []])
                self.category[asin] = category
                self.by_category.setdefault(category, []).append(asin)

        # the paraphrase insurance policy (IMPORTANT.md §5): the global popularity ordering
        self.global_pool = sorted(self.popularity, key=self.popularity.get, reverse=True)[:2000]
        self._category_tokens = {category: tokens(category) for category in self.by_category}

    # --- pools -------------------------------------------------------------
    def pool(self, category: str | None) -> list[str]:
        """Candidate universe for a stated category. Never empty (spec 3.2)."""
        if category and category in self.by_category:
            return self.by_category[category]
        if category:
            lowered = category.lower()
            hits = [c for c in self.by_category if lowered in c.lower() or c.lower() in lowered]
            if hits:
                return [asin for hit in hits[:5] for asin in self.by_category[hit]]
        return self.global_pool

    def best_category(self, text: str) -> str | None:
        """Fuzzy category resolution for when the opener was reworded and the template missed.

        Two passes: the longest category name quoted verbatim wins, otherwise the best token
        overlap. Scored `hits × coverage` rather than coverage alone — coverage alone lets a
        one-word category ("Shirts T-Shirts") beat the three-word category the shopper actually
        named ("Shirts Tanks Tops"), which was worth 21 lost sessions under stress.
        """
        lowered = (text or "").lower()
        quoted = [c for c in self.by_category if c.lower() in lowered]
        if quoted:
            return max(quoted, key=len)
        ranked = self.ranked_categories(text, top=1)
        return ranked[0][0] if ranked else None

    def ranked_categories(self, text: str, top: int = 3) -> list[tuple[str, float]]:
        """Categories by `hits² / |category tokens|`, best first."""
        wanted = tokens(text)
        if not wanted:
            return []
        scored = []
        for category, category_tokens in self._category_tokens.items():
            hit = len(wanted & category_tokens)
            if hit:
                scored.append((category, hit * hit / (len(category_tokens) or 1)))
        scored.sort(key=lambda row: -row[1])
        return scored[:top]

    def hedge(self, text: str, keep: float = 0.6, cap: int = 4000) -> str | None:
        """When the wording no longer pins one category, search the union of the plausible ones.

        R1 relaxes rather than shrinks, so a slightly larger pool costs ranking, while the wrong
        pool costs the session outright. Measured: 15% of model-paraphrased openers resolve to the
        wrong category, and those are guaranteed misses. Only ever used on the fuzzy path — a
        template-matched category is exact and is used directly.
        """
        lowered = (text or "").lower()
        quoted = [c for c in self.by_category if c.lower() in lowered]
        if quoted:
            return max(quoted, key=len)
        ranked = self.ranked_categories(text)
        if not ranked:
            return None
        best = ranked[0][1]
        chosen = [category for category, score in ranked if score >= keep * best]
        if len(chosen) == 1:
            return chosen[0]
        key = " | ".join(chosen)
        if key not in self.by_category:
            union: list[str] = []
            for category in chosen:
                union.extend(self.by_category[category])
            self.by_category[key] = union[:cap]
        return key

    def pool_features(self, category: str | None) -> PoolFeatures:
        key = category if category in self.by_category else "\0global"
        cached = self._pools.get(key)
        if cached is not None:
            return cached
        asins = self.pool(category)
        features = PoolFeatures(asins)
        for asin in asins:
            strings = self.spec_strings[asin]
            features.phrases[asin] = frozenset(self.card_strings[asin])
            pairs: set[tuple[str, str]] = set()
            for text in strings:
                pairs.update(normalise(text))
            features.pairs[asin] = frozenset(pairs)
            features.tokens[asin] = tokens(" ".join(strings) + " " + self.title[asin])
        self._pools[key] = features
        return features
