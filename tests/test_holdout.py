"""M8 — the immutable 140/60 split.

R1 defect 3 and R2 defect 1 are both "no held-out evaluation": every threshold in both roads was chosen
on all 200 public sessions, and a bootstrap CI resamples the very sessions the thresholds were tuned on,
so it cannot detect overfitting. R3 adds calibration parameters, making it the road most able to overfit
invisibly — so this lands before any R3 parameter is chosen.

Disjoint on sample_id AND target ASIN: the same product appearing in both halves leaks the answer.
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import holdout  # noqa: E402


class TestM8Holdout(unittest.TestCase):
    def setUp(self) -> None:
        self.split = holdout.load()

    def test_split_is_140_60(self) -> None:
        """M8: 140 to tune on, 60 held back."""
        self.assertEqual(len(self.split["train"]), 140)
        self.assertEqual(len(self.split["test"]), 60)

    def test_sample_ids_are_disjoint(self) -> None:
        """M8: the obvious leak."""
        self.assertEqual(set(self.split["train"]) & set(self.split["test"]), set())

    def test_target_asins_are_disjoint(self) -> None:
        """M8: the non-obvious leak — the same target product in both halves leaks the answer."""
        by_id = holdout.targets()
        train = {by_id[s] for s in self.split["train"]}
        test = {by_id[s] for s in self.split["test"]}
        self.assertEqual(train & test, set(), "a target ASIN appears in both halves")

    def test_scenarios_are_stratified(self) -> None:
        """M8: the four scenarios must both appear in proportion, or the 60 measures something else."""
        by_id = holdout.scenarios()
        train = Counter(by_id[s] for s in self.split["train"])
        test = Counter(by_id[s] for s in self.split["test"])
        for scenario in set(by_id.values()):
            total = train[scenario] + test[scenario]
            self.assertAlmostEqual(test[scenario] / total, 0.30, delta=0.12,
                                   msg=f"{scenario}: {test[scenario]}/{total} held out")

    def test_manifest_is_immutable(self) -> None:
        """M8: a split that can drift is not a held-out set. The hash is the lock."""
        self.assertEqual(holdout.content_hash(), self.split["hash"],
                         "the manifest changed - every held-out number taken before now is void")


if __name__ == "__main__":
    unittest.main()
