"""R2-A1: src/common/simulator.py must behave identically to the kit's evaluator over all 50,000 rows.

Importing the evaluator is legal HERE (a test script sits outside the agent import cycle) and is the whole
point: this is the only place the copy is checked against the original.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "techjam-conversational-search-main"))

from evaluator import local_evaluator as kit  # noqa: E402
from src import simulator as ours  # noqa: E402


class TestSimulatorParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.products = [
            json.loads(line)
            for line in (ROOT / "data" / "catalog.jsonl").open(encoding="utf-8")
        ]

    def test_intent_card_parity_all_rows(self) -> None:
        """R2-A1: every catalog row produces an identical intent card."""
        mismatches = [
            p["parent_asin"] for p in self.products
            if ours.intent_card(p) != kit.intent_card(p)
        ]
        self.assertEqual(mismatches[:5], [], f"{len(mismatches)} intent_card mismatches")

    def test_coarse_category_parity_all_rows(self) -> None:
        """R2-A1: every catalog row produces an identical coarse category."""
        mismatches = [
            p["parent_asin"] for p in self.products
            if ours.coarse_category([str(v) for v in p.get("categories") or []])
            != kit.coarse_category([str(v) for v in p.get("categories") or []])
        ]
        self.assertEqual(mismatches[:5], [], f"{len(mismatches)} coarse_category mismatches")

    def test_classify_constraint_parity_over_real_constraints(self) -> None:
        """R2-A1: identical classification over every constraint the catalog can produce."""
        mismatches = []
        for p in self.products[:20000]:
            card = ours.intent_card(p)
            for value in card["hard_constraints"] + card["soft_preferences"]:
                if ours.classify_constraint(value) != kit.classify_constraint(value):
                    mismatches.append(value)
        self.assertEqual(mismatches[:5], [], f"{len(mismatches)} classify mismatches")

    def test_allowed_attributes_match(self) -> None:
        """R2-A1: the attribute vocabulary has not drifted from the kit."""
        self.assertEqual(ours.ALLOWED_ATTRIBUTES, kit.ALLOWED_ATTRIBUTES)


if __name__ == "__main__":
    unittest.main()
