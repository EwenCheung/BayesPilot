"""Route behaviour, including the determinism the whole harness rests on.

A score that changes between processes is not a score. Python salts string hashing per interpreter, so
anything that iterates a set and truncates silently produces a different index every run — the bug this
module exists to prevent recurring.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.catalog import CatalogIndex  # noqa: E402
from src.r2.routes import LexicalRoute, PopularityRoute, Query, SpecPhraseRoute  # noqa: E402

CATALOG = ROOT / "assets" / "catalog.jsonl"


class TestRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = CatalogIndex(CATALOG)

    def test_popularity_is_pool_normalized_and_paraphrase_blind(self) -> None:
        """The popularity route must ignore the query entirely — that is why it cannot be broken."""
        route = PopularityRoute(self.index)
        pool = self.index.by_cat[next(iter(self.index.by_cat))]
        a = route.score(Query(text="anything"), pool)
        b = route.score(Query(text="something totally different"), pool)
        self.assertEqual(a, b)
        self.assertLessEqual(max(a.values()), 1.0)

    def test_spec_phrase_gives_full_credit_for_an_exact_catalog_string(self) -> None:
        """An exact spec string is the strongest evidence available and must score highest."""
        route = SpecPhraseRoute(self.index)
        asin = next(a for a in self.index.products if len(self.index.phrases[a]) >= 2)
        phrase = sorted(self.index.phrases[asin])[0]
        pool = self.index.by_cat[self.index.coarse[asin]]
        scores = route.score(Query(constraints=[(phrase, 1.0)]), pool)
        # The absolute value is a fusion detail (an exactly-covered candidate earns the coverage
        # bonus on top). The property that matters is that nothing in the pool outscores it.
        self.assertEqual(scores.get(asin), max(scores.values()))

    def test_spec_phrase_degrades_instead_of_collapsing_on_paraphrase(self) -> None:
        """R2's whole bet (decision D4): a reworded constraint must still score, not drop to zero.

        R1's frozenset intersection returns nothing here. That cliff is the private-set risk.
        """
        route = SpecPhraseRoute(self.index)
        asin = next(a for a in self.index.products
                    if any(len(p.split()) >= 4 for p in self.index.phrases[a]))
        phrase = next(p for p in sorted(self.index.phrases[asin]) if len(p.split()) >= 4)
        reworded = " ".join(reversed(phrase.split())).lower() + " please"
        pool = self.index.by_cat[self.index.coarse[asin]]

        exact = route.score(Query(constraints=[(phrase, 1.0)]), pool)
        fuzzy = route.score(Query(constraints=[(reworded, 1.0)]), pool)
        self.assertEqual(exact.get(asin), max(exact.values()))
        self.assertGreater(fuzzy.get(asin, 0.0), 0.0, "paraphrase collapsed the route to zero")
        self.assertLess(fuzzy[asin], exact[asin], "paraphrase must cost score, not nothing")

    def test_spec_phrase_abstains_with_no_constraints(self) -> None:
        """Abstention must be distinguishable from scoring zero, so fusion can ignore it."""
        self.assertEqual(SpecPhraseRoute(self.index).score(Query(), ["X"]), {})

    def test_lexical_index_is_deterministic_across_processes(self) -> None:
        """The bug this test exists for: list(set)[:cap] picks a different subset every interpreter.

        Salted string hashing made the reported TechnicalScore drift between identical runs.
        """
        probe = (
            "import sys; sys.path.insert(0, %r)\n"
            "from src.common.catalog import CatalogIndex\n"
            "from src.r2.routes import LexicalRoute\n"
            "i = CatalogIndex(%r); r = LexicalRoute(i)\n"
            "a = sorted(i.products)[0]\n"
            "print(len(r.idf), '|', ','.join(sorted(r.doc_tokens[a])))\n"
        ) % (str(ROOT), str(CATALOG))
        runs = [
            subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                           cwd=ROOT).stdout.strip()
            for _ in range(2)
        ]
        self.assertEqual(runs[0], runs[1], "lexical index differs between processes")

    def test_lexical_scores_a_product_by_its_own_words(self) -> None:
        route = LexicalRoute(self.index)
        asin = next(a for a in self.index.products if self.index.products[a].get("title"))
        pool = self.index.by_cat[self.index.coarse[asin]]
        scores = route.score(
            Query(category=self.index.coarse[asin],
                  constraints=[(str(self.index.products[asin]["title"]), 1.0)]),
            pool,
        )
        self.assertGreater(scores.get(asin, 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
