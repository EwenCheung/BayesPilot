"""Level 1 of the belief — a posterior over the 1,115 coarse categories (00-r3-spec.md §2.4).

What this replaces:

    scored.append((category, hit * hit / (len(category_tokens) or 1)))   # R1, and R2 is no better
    chosen = [c for c, s in ranked[:3] if s >= 0.6 * best]

Both roads pick the pool by counting words shared with the category name, then hedge over an arbitrary
top-3 at a tuned 0.6. It is the earliest decision in a session and unrecoverable when wrong: at L3 it is
right 82.5% of the time and leaves the target outside the searched pool in 7.5% of sessions (D13).

Two things were learned by looking at the 35 L3 failures rather than guessing (D14):

1. **`coarse_category` is hierarchical** — the evaluator joins the last two taxonomy levels, so
   "Tees & Blouses Tunics" has six siblings. When a shopper says only "tees & blouses", the child is
   genuinely not in the message: no resolver can pick it, and `best()` is information-limited at
   ~1-in-7. **The pool, however, can hold every sibling** — which is precisely what a distribution does
   and an argmax-plus-hedge cannot.
2. **Morphology decides real sessions.** "womens hoodies" did not match "Women Hoodies", leaving
   "hoodies" as the only hit — which tied "Women Hoodies" with "Men Hoodies", and the tie broke wrong.

A per-category language model over product titles was tried first and lost badly (0.525 against 0.825):
the scaffold words outvote the one token carrying the category. Measured, recorded in D14, not kept.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path

from src.understand.attributes import tokens
from src.simulator import coarse_category

TAU_MASS = 0.90       # widen until this much posterior mass is covered  (chosen on the 140)
TEMPERATURE = 2.0     # how sharply score differences become belief (chosen on the 140)
POOL_CAP = 8000       # latency bound (R3-A14), not a modelling choice
QUOTE_BONUS = 3.0     # the whole category name present verbatim is much stronger than token overlap


def stem(word: str) -> str:
    """Crude, consistent, applied to BOTH sides. `womens`->`women`, `tees`->`tee`.

    Correctness matters less than symmetry here: the only job is that the shopper's word and the
    catalog's word land on the same string.
    """
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def stems(text: str) -> set[str]:
    return {stem(w) for w in tokens(text)}


class CategoryBelief:
    """P(category | utterance) — a distribution, so hedging is a consequence, not a constant."""

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.by_category: dict[str, list[str]] = defaultdict(list)
        with Path(catalog_path).open(encoding="utf-8") as handle:
            self._ingest(handle)

    def _ingest(self, handle) -> None:
        for line in handle:
            product = json.loads(line)
            asin = product.get("parent_asin")
            if asin:
                self.by_category[coarse_category(product.get("categories") or [])].append(asin)

        self.categories = sorted(self.by_category)
        self._idx = {c: i for i, c in enumerate(self.categories)}
        self._stems = [stems(c) for c in self.categories]
        self._lower = [c.lower() for c in self.categories]

        # a token shared by many categories says little; one unique to a few says a lot
        df: dict[str, int] = defaultdict(int)
        for s in self._stems:
            for token in s:
                df[token] += 1
        n = len(self.categories)
        self._idf = {t: math.log(n / d) for t, d in df.items()}

        # prior ∝ catalog share: a category holding more products is a likelier destination
        total = sum(len(v) for v in self.by_category.values())
        self._log_prior = [math.log(len(self.by_category[c]) / total) for c in self.categories]

    def _scores(self, message: str) -> list[float]:
        want = stems(message)
        lowered = (message or "").lower()
        out = []
        for i, cat_stems in enumerate(self._stems):
            shared = want & cat_stems
            if not shared:
                out.append(-30.0)
                continue
            # R1's hits²/|tokens| shape — reward covering the category, penalise unmatched tokens —
            # but weighted by how informative each shared token is.
            weight = sum(self._idf.get(t, 0.0) for t in shared)
            coverage = len(shared) / len(cat_stems)
            score = weight * coverage
            if self._lower[i] in lowered:
                score += QUOTE_BONUS * weight
            out.append(score)
        return out

    def posterior(self, message: str) -> list[float]:
        scores = self._scores(message)
        logits = [s / TEMPERATURE + 0.25 * p for s, p in zip(scores, self._log_prior)]
        peak = max(logits)
        weights = [math.exp(l - peak) for l in logits]
        mass = sum(weights)
        return [w / mass for w in weights]

    def ranked(self, message: str) -> list[tuple[str, float]]:
        post = self.posterior(message)
        return [(self.categories[i], post[i])
                for i in sorted(range(len(post)), key=lambda i: -post[i])]

    def best(self, message: str) -> str:
        post = self.posterior(message)
        return self.categories[max(range(len(post)), key=lambda i: post[i])]

    def pool(self, message: str, tau: float = TAU_MASS, cap: int = POOL_CAP) -> list[str]:
        """Smallest set of categories covering `tau` of the posterior, as ASINs.

        R1's hedge without R1's two constants: a confident belief returns one category, a belief spread
        over seven siblings returns all seven. `cap` bounds latency, nothing else.
        """
        asins: list[str] = []
        covered = 0.0
        for category, mass in self.ranked(message):
            asins.extend(self.by_category[category])
            covered += mass
            if covered >= tau or len(asins) >= cap:
                break
        return asins[:cap]
