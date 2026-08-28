"""CatalogIndex — built once, shared by every session.

The evaluator constructs a single Agent for all 200 sessions, so index build cost amortizes to zero and a
heavy in-memory index is free (IMPORTANT.md §2). Nothing here is per-session; all session state lives in
SessionState.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from ..common.simulator import coarse_category, intent_card

TOKEN_RE = re.compile(r"[a-z0-9]+")

# Deliberately small. These words appear in so many spec strings that matching on them is noise, but
# anything domain-bearing ("cotton", "buckle", "womens") must survive.
STOPWORDS = frozenset("""
a an and are as at be but by for from in is it of on or the to with this that these those
your you our we they i me my
""".split())


def content_tokens(text: str) -> set[str]:
    return {t for t in TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in STOPWORDS}


class CatalogIndex:
    """Everything derivable from the frozen catalog, precomputed."""

    def __init__(self, catalog_path: str | Path) -> None:
        self.products: dict[str, dict] = {}
        self.coarse: dict[str, str] = {}
        self.by_cat: dict[str, list[str]] = {}
        self.pop: dict[str, int] = {}
        self.log_pop: dict[str, float] = {}
        self.phrases: dict[str, frozenset[str]] = {}
        self.tokens: dict[str, frozenset[str]] = {}

        with Path(catalog_path).open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                asin = str(product["parent_asin"])
                self.products[asin] = product

                cat = coarse_category([str(v) for v in product.get("categories") or []])
                self.coarse[asin] = cat
                self.by_cat.setdefault(cat, []).append(asin)

                reviews = product.get("rating_number") or 0
                self.pop[asin] = reviews
                self.log_pop[asin] = math.log1p(reviews)

                # The inversion surface: exactly what this product would say as a hidden target.
                card = intent_card(product)
                spec = frozenset(card["hard_constraints"]) | frozenset(card["soft_preferences"])
                self.phrases[asin] = spec
                self.tokens[asin] = frozenset(content_tokens(" ".join(spec)))

        # Popularity is compared within a category, so normalize per category rather than globally —
        # "well reviewed for a hoop earring" is the signal, not "well reviewed for a shoe".
        self.max_log_pop: dict[str, float] = {
            cat: max((self.log_pop[a] for a in asins), default=1.0) or 1.0
            for cat, asins in self.by_cat.items()
        }

    def __len__(self) -> int:
        return len(self.products)

    def candidates(self, category: str | None, cap: int = 4000) -> list[str]:
        """Candidate pool for a turn.

        A known category scopes hard (median 181 products, max 1354). With no category yet — a browsing
        turn 1 before anything is parsed — fall back to the globally most-reviewed products, which is the
        popularity prior doing the recall job.
        """
        if category and category in self.by_cat:
            return self.by_cat[category]
        if not hasattr(self, "_global_top"):
            self._global_top = sorted(self.products, key=lambda a: -self.pop[a])[:cap]
        return self._global_top

    def resolve_category(self, stated: str | None) -> str | None:
        """Map a stated category to a known coarse category.

        Exact hit is the normal case — the simulator emits `coarse_category` verbatim. Under paraphrase
        the wording drifts, so fall back to best token overlap, which is what keeps the whole pipeline
        from losing its candidate pool when the carrier sentence is rewritten.
        """
        if not stated:
            return None
        if stated in self.by_cat:
            return stated
        lowered = stated.lower().strip()
        for cat in self.by_cat:
            if cat.lower() == lowered:
                return cat
        wanted = content_tokens(stated)
        if not wanted:
            return None
        best, best_score = None, 0.0
        for cat in self.by_cat:
            cat_tokens = content_tokens(cat)
            if not cat_tokens:
                continue
            overlap = len(wanted & cat_tokens)
            if not overlap:
                continue
            # Favour categories that are mostly covered by what the customer said, and break ties
            # toward the larger pool so we do not strand ourselves in a 3-product category.
            score = overlap / len(cat_tokens) + 0.001 * math.log1p(len(self.by_cat[cat]))
            if score > best_score:
                best, best_score = cat, score
        return best
