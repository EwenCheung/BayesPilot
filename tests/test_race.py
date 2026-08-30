"""M3 — one runner for every road, and it must reproduce what each road published.

The merge's whole purpose is that R1's and R2's numbers become comparable (04-merge-plan.md §1).
That is only true if the unified runner reproduces each road's own clean score exactly. If it does
not, the merge changed behaviour somewhere and every number downstream is unverifiable.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import race  # noqa: E402


class TestM3RoadsReproduce(unittest.TestCase):
    def test_r1_reproduces_its_published_clean_score(self) -> None:
        """M3: R1 == 0.9597 (docs/r1-exploration/SUMMARY.md §2)."""
        self.assertAlmostEqual(race.score_road("r1"), 0.9597, places=3)

    def test_r2_reproduces_its_published_clean_score(self) -> None:
        """M3: R2 == 0.9707 (docs/r2-exploration/SUMMARY.md §2)."""
        self.assertAlmostEqual(race.score_road("r2"), 0.9707, places=3)

    def test_every_road_is_reachable_by_name(self) -> None:
        """M3: the race enumerates roads; adding R3 must not need a new runner."""
        self.assertIn("r1", race.ROADS)
        self.assertIn("r2", race.ROADS)


if __name__ == "__main__":
    unittest.main()
