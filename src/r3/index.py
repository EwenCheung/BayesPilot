"""R3's single item index — one pass over the catalog, everything the belief needs.

R1 and R2 each built their own `CatalogIndex` with different APIs; R3 builds one, because a posterior
that has to reconcile two views of the same catalog is not one model. Per-pool features are computed
lazily and cached, since a session touches at most a handful of category pools.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from src.common.attributes import normalise, tokens
from src.common.simulator import _flatten_values, intent_card


TRUSTED_ALIASES: dict[str, dict[str, str]] = {
    "material": {
        "polyster": "polyester",
        "polyesther": "polyester",
        "cotten": "cotton",
        "pleather": "leather",
    },
    "feature": {"comfy": "comfortable", "waterproofed": "waterproof"},
    "size": {
        "x large": "xl", "extra large": "xl", "xlarge": "xl",
        "x small": "xs", "extra small": "xs", "xsmall": "xs",
    },
    "use_case": {
        "washer safe": "machine wash", "machine washable": "machine wash",
        "wash by hand": "hand wash", "hand washable": "hand wash",
        "from abroad": "imported", "shipped from abroad": "imported",
    },
}
AMBIGUOUS_FRAGMENTS = frozenset({"poly", "reg", "syn", "art"})


class ItemIndex:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.title: dict[str, str] = {}
        self.log_pop: dict[str, float] = {}
        self.card: dict[str, tuple[str, ...]] = {}     # the item's own intent-card constraint strings
        self.spec: dict[str, tuple[str, ...]] = {}     # its features + details, unprocessed
        self._pairs: dict[str, frozenset[tuple[str, str]]] = {}
        self._card_pairs: dict[str, frozenset[tuple[str, str]]] = {}
        self._tokens: dict[str, frozenset[str]] = {}
        # R2's lexical surface: deliberately DIFFERENT from the spec surface above, so the two are
        # not the same evidence counted twice (ported from src/r2/routes.py LexicalRoute).
        self.lexical_text: dict[str, str] = {}
        self._canonical_counts: dict[str, Counter[str]] = {}
        self._canonical_exact: dict[str, dict[str, str]] = {}
        self._canonical_tokens: dict[str, dict[str, set[str]]] = {}
        self._canonical_values: dict[str, dict[str, Counter[str]]] = {}
        self._canonical_concept_asins: dict[tuple[str, str], set[str]] = {}
        self._canonical_ready = False

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
            parts = [self.title[asin], str(product.get("store") or "")]
            parts.extend(_flatten_values(product.get("categories")))
            parts.extend(_flatten_values(product.get("features"))[:8])
            self.lexical_text[asin] = " ".join(parts)

    @staticmethod
    def _canonical_key(value: str) -> str:
        return re.sub(r"[^a-z0-9%$]+", " ", value.lower()).strip()

    @classmethod
    def _value_key(cls, attribute: str, value: str) -> str:
        key = next((normal for found, normal in normalise(value) if found == attribute), "")
        key = cls._canonical_key(key or value)
        if attribute == "size":
            key = TRUSTED_ALIASES["size"].get(key, key)
        if attribute == "use_case":
            key = TRUSTED_ALIASES["use_case"].get(key, key)
        key = TRUSTED_ALIASES.get(attribute, {}).get(key, key)
        if attribute == "material" and "entirely" in key:
            key = key.replace("made entirely of ", "").replace("entirely ", "").strip()
        return key

    def _build_canonical_index(self) -> None:
        if self._canonical_ready:
            return
        counts_by_attribute: dict[str, Counter[str]] = defaultdict(Counter)
        values_by_attribute: dict[str, dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        concept_asins: dict[tuple[str, str], set[str]] = defaultdict(set)
        for asin, labels in self.card.items():
            for label in labels:
                for attribute, value in normalise(label):
                    value_key = self._value_key(attribute, value)
                    counts_by_attribute[attribute][label] += 1
                    values_by_attribute[attribute][value_key][label] += 1
                    concept_asins[(attribute, value_key)].add(asin)
        self._canonical_counts = dict(counts_by_attribute)
        self._canonical_values = {
            attribute: dict(values) for attribute, values in values_by_attribute.items()
        }
        self._canonical_concept_asins = dict(concept_asins)
        for attribute, counts in self._canonical_counts.items():
            exact: dict[str, str] = {}
            postings: dict[str, set[str]] = defaultdict(set)
            for label, _frequency in counts.most_common():
                exact.setdefault(self._canonical_key(label), label)
                for token in tokens(label):
                    postings[token].add(label)
            self._canonical_exact[attribute] = exact
            self._canonical_tokens[attribute] = dict(postings)
        self._canonical_ready = True

    def exact_canonical(self, attribute: str, value: str) -> str | None:
        """Return the catalog's exact spelling, never model-generated text."""
        self._build_canonical_index()
        literal = self._canonical_exact.get(attribute, {}).get(self._canonical_key(value))
        if literal:
            return literal
        phrase_key = self._canonical_key(value)
        if phrase_key in AMBIGUOUS_FRAGMENTS:
            return None
        aliased = TRUSTED_ALIASES.get(attribute, {}).get(phrase_key, phrase_key)
        equivalents = self._canonical_values.get(attribute, {}).get(aliased)
        return self._representative(aliased, equivalents) if equivalents else None

    def is_trusted_alias(self, attribute: str, evidence: str, value: str) -> bool:
        """Whether an explicit evidence phrase safely entails the model's normalized value."""
        evidence_key = self._canonical_key(evidence)
        value_key = self._value_key(attribute, value)
        for alias, target in TRUSTED_ALIASES.get(attribute, {}).items():
            if alias in evidence_key and target == value_key:
                return True
        return False

    def _representative(self, value_key: str, labels: Counter[str] | None) -> str | None:
        if not labels:
            return None
        # Prefer a concise label whose literal spelling is the normalized concept. This prevents an
        # abbreviation such as ``poly`` from landing on a long cotton/polyester blend merely because
        # that raw label happens to contain the token.
        return max(
            labels,
            key=lambda label: (
                self._canonical_key(label) == value_key,
                labels[label],
                -len(label),
                label,
            ),
        )

    def canonical_candidate_records(
        self, attribute: str, phrase: str, limit: int = 8
    ) -> list[dict[str, object]]:
        """Retrieve concept-level candidates using aliases, prefixes, typos and token overlap."""
        self._build_canonical_index()
        phrase_key = self._canonical_key(phrase)
        if not phrase_key:
            return []
        aliased = TRUSTED_ALIASES.get(attribute, {}).get(phrase_key, phrase_key)
        phrase_words = set(aliased.split())
        rows: list[dict[str, object]] = []
        for value_key, labels in self._canonical_values.get(attribute, {}).items():
            value_words = set(value_key.split())
            exact = aliased == value_key
            overlap = len(phrase_words & value_words) / max(1, len(phrase_words | value_words))
            prefix = 0.0
            for wanted in phrase_words:
                for actual in value_words:
                    if min(len(wanted), len(actual)) >= 3 and (
                        actual.startswith(wanted) or wanted.startswith(actual)
                    ):
                        prefix = max(prefix, min(len(wanted), len(actual)) / max(len(wanted), len(actual)))
            similarity = SequenceMatcher(None, aliased, value_key).ratio()
            if not exact and overlap == 0 and prefix == 0 and similarity < 0.72:
                continue
            score = 10.0 if exact else 3.0 * overlap + 2.0 * prefix + similarity
            label = self._representative(value_key, labels)
            if not label:
                continue
            rows.append({
                "label": label,
                "attribute": attribute,
                "value": value_key,
                "score": score,
                "support": len(self._canonical_concept_asins.get((attribute, value_key), ())),
            })
        rows.sort(key=lambda row: (-float(row["score"]), -int(row["support"]), str(row["label"])))
        return rows[:limit]

    def canonical_candidates(self, attribute: str, phrase: str, limit: int = 8) -> list[str]:
        """Retrieve plausible real labels for constrained LLM selection.

        No shared content token means abstention. This prevents vague phrases such as "from abroad"
        from being forced into a specific unsupported label such as "Imported from Europe".
        """
        return [str(row["label"]) for row in self.canonical_candidate_records(attribute, phrase, limit)]

    def concept_support(self, attribute: str, value: str, candidates: list[str] | None = None) -> int:
        """Count catalog support, optionally within a category-derived product pool."""
        self._build_canonical_index()
        asins = self._canonical_concept_asins.get((attribute, self._value_key(attribute, value)), set())
        return len(asins) if candidates is None else len(asins.intersection(candidates))

    def pairs(self, asin: str) -> frozenset[tuple[str, str]]:
        got = self._pairs.get(asin)
        if got is None:
            out: set[tuple[str, str]] = set()
            for text in self.spec[asin]:
                out.update(normalise(text))
            got = self._pairs[asin] = frozenset(out)
        return got

    def card_pairs(self, asin: str) -> frozenset[tuple[str, str]]:
        """Canonical concepts present in the evaluator's four target constraints."""
        got = self._card_pairs.get(asin)
        if got is None:
            out: set[tuple[str, str]] = set()
            for text in self.card[asin]:
                out.update(normalise(text))
            got = self._card_pairs[asin] = frozenset(out)
        return got

    def tokens(self, asin: str) -> frozenset[str]:
        got = self._tokens.get(asin)
        if got is None:
            got = self._tokens[asin] = tokens(" ".join(self.spec[asin]) + " " + self.title[asin])
        return got
