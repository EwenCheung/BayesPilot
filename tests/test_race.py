"""Every road runs through the shared evaluator on train-derived smoke sessions."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import race  # noqa: E402


class TestM3RoadsReproduce(unittest.TestCase):
    def test_r1_runs_on_train_smoke_subset(self) -> None:
        result = race.run_road("r1", sample_limit=40)
        self.assertEqual(result["sample_count"], 40)
        self.assertGreaterEqual(result["recommended_technical_score"], 0.0)

    def test_r2_runs_on_train_smoke_subset(self) -> None:
        result = race.run_road("r2", sample_limit=40)
        self.assertEqual(result["sample_count"], 40)
        self.assertGreaterEqual(result["recommended_technical_score"], 0.0)

    def test_every_road_is_reachable_by_name(self) -> None:
        """M3: the race enumerates roads; adding R3 must not need a new runner."""
        self.assertIn("r1", race.ROADS)
        self.assertIn("r2", race.ROADS)


if __name__ == "__main__":
    unittest.main()
