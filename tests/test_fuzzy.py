"""R5-A12 / R5-A13 — fuzzy canonicalisation must repair typos WITHOUT inventing constraints.

The measurement that motivates these tests is in `src/r5/fuzzy.py`'s docstring: correcting against
the whole catalog vocabulary maps `browsing -> brown` (a colour) and `wait -> waist` (a size), which
injects evidence the shopper never gave. A corrector that only raises the hit rate on typos while
quietly doing that is a net loss, so the guard is tested directly rather than inferred from a score.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CATALOG = ROOT / "techjam-conversational-search-main" / "data" / "catalog.jsonl"


class TestFuzzyCanon(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from src.r3.category import CategoryBelief
        from src.r3.index import ItemIndex
        from src.r5.fuzzy import FuzzyCanon
        index = ItemIndex(CATALOG)
        cls.canon = FuzzyCanon(CategoryBelief(CATALOG).by_category.keys(), index.lexical_text)

    def test_repairs_misspelled_category_words(self) -> None:
        """R5-A12: a typo'd category word gains its correction as a candidate."""
        for typo, wanted in (("snekers", "sneakers"), ("bracelt", "bracelets"), ("dres", "dress")):
            got = self.canon.expand(f"need {typo} pls")
            self.assertIn(wanted, got.split(), f"{typo!r} -> {got!r}")

    def test_keeps_the_original_word(self) -> None:
        """R5-A12: expansion, never replacement — `sirt` ties shirt/skirt at 0.889 and difflib
        breaks that tie ALPHABETICALLY. Dropping the original would stake the turn on `k`."""
        got = self.canon.expand("blue sirt").split()
        self.assertIn("sirt", got)
        self.assertIn("shirt", got)

    def test_does_not_invent_constraints_from_ordinary_english(self) -> None:
        """R5-A13: the guard. These are correctly-spelled conversational words; `brown` is a COLOR
        and `waist` a SIZE, so a correction here fabricates evidence the shopper never gave."""
        for word, forbidden in (("browsing", "brown"), ("haves", "hanes"),
                                ("browse", "rows"), ("matters", "masters"),
                                ("settled", "styled"), ("decided", "decide")):
            got = self.canon.expand(f"just {word} around").split()
            self.assertNotIn(forbidden, got, f"{word!r} was corrupted into {forbidden!r}")

    def test_known_residual_leak_is_pinned(self) -> None:
        """R5-A13 ⚠️ NOT FIXED, pinned so it stays visible: `wait -> waist` scores 0.889, the SAME
        ratio as `sirt -> shirt`. No cutoff separates them, so raising the floor to kill this leak
        also kills the repairs the module exists for. The mitigation is structural rather than
        threshold-based: expansion keeps `wait`, so the false candidate competes with the true
        evidence instead of replacing it, and a term with no opinion cancels (`likelihood.py`).
        If this test starts FAILING, the guard improved — update it, do not delete it."""
        self.assertIn("waist", self.canon.expand("just wait around").split())

    def test_catalog_words_are_never_touched(self) -> None:
        """R5-A13: a word the catalog genuinely uses is not a typo, however odd it looks."""
        message = "looking for leather oxfords in black"
        self.assertEqual(self.canon.expand(message), message)

    def test_never_raises(self) -> None:
        for message in ("", "?????", "\x00\x01", "a" * 3000, None):
            self.canon.expand(message or "")


class TestFuzzyShipsOff(unittest.TestCase):
    def test_defaults_off(self) -> None:
        """R5-A8: every R5 mechanism defaults off, so a default R5 is a default R4."""
        from src.r5.flags import Flags
        self.assertFalse(Flags().fuzzy_expand)


if __name__ == "__main__":
    unittest.main()
