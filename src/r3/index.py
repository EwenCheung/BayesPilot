"""R3's single item index — one pass over the catalog, everything the belief needs.

R1 and R2 each built their own `CatalogIndex` with different APIs; R3 builds one, because a posterior
that has to reconcile two views of the same catalog is not one model. Per-pool features are computed
lazily and cached, since a session touches at most a handful of category pools.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from src.common.attributes import normalise, tokens
from src.common.simulator import _flatten_values, intent_card


class ItemIndex:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.title: dict[str, str] = {}
        self.log_pop: dict[str, float] = {}
        self.card: dict[str, tuple[str, ...]] = {}     # the item's own intent-card constraint strings
        self.spec: dict[str, tuple[str, ...]] = {}     # its features + details, unprocessed
        self._pairs: dict[str, frozenset[tuple[str, str]]] = {}
        self._tokens: dict[str, frozenset[str]] = {}

        with Path(catalog_path).open(encoding="utf-8") as handle:
            self._ingest(handle)

    def _ingest(self, handle) -> None:
        for line in handle:
            product = json.loads(line)
            asin = product.get("parent_asin")
            if not asin:
                continue
            self.title[asin] = product.get("title") or ""
            self.log_pop[asin] = math.log1p(float(product.get("rating_number") or 0))
            card = intent_card(product)
            # ⚠️ a tuple in the simulator's own order, never a set: CPython salts string hashing per
            # process, so a set here made the score drift between identical runs in BOTH roads.
            self.card[asin] = tuple(card.get("hard_constraints", ())) + tuple(
                card.get("soft_preferences", ()))
            self.spec[asin] = tuple(_flatten_values(product.get("features"))) + tuple(
                _flatten_values(product.get("details")))

    def pairs(self, asin: str) -> frozenset[tuple[str, str]]:
        got = self._pairs.get(asin)
        if got is None:
            out: set[tuple[str, str]] = set()
            for text in self.spec[asin]:
                out.update(normalise(text))
            got = self._pairs[asin] = frozenset(out)
        return got

    def tokens(self, asin: str) -> frozenset[str]:
        got = self._tokens.get(asin)
        if got is None:
            got = self._tokens[asin] = tokens(" ".join(self.spec[asin]) + " " + self.title[asin])
        return got
