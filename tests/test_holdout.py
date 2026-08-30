"""Locked train/validation development boundary; public and test are absent."""
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

    def test_split_is_8400_2800(self) -> None:
        self.assertEqual(len(self.split["train"]), 8400)
        self.assertEqual(len(self.split["validation"]), 2800)

    def test_sample_ids_are_disjoint(self) -> None:
        """M8: the obvious leak."""
        self.assertEqual(set(self.split["train"]) & set(self.split["validation"]), set())

    def test_target_asins_are_disjoint(self) -> None:
        """M8: the non-obvious leak — the same target product in both halves leaks the answer."""
        by_id = holdout.targets()
        train = {by_id[s] for s in self.split["train"]}
        validation = {by_id[s] for s in self.split["validation"]}
        self.assertEqual(train & validation, set(), "a target ASIN appears in both halves")

    def test_scenarios_are_stratified(self) -> None:
        """M8: the four scenarios must both appear in proportion, or the 60 measures something else."""
        by_id = holdout.scenarios()
        train = Counter(by_id[s] for s in self.split["train"])
        validation = Counter(by_id[s] for s in self.split["validation"])
        for scenario in set(by_id.values()):
            self.assertEqual(train[scenario] / len(self.split["train"]),
                             validation[scenario] / len(self.split["validation"]))

    def test_manifest_is_immutable(self) -> None:
        """M8: a split that can drift is not a held-out set. The hash is the lock."""
        self.assertEqual(holdout.content_hash(), self.split["hash"],
                         "the manifest changed - every held-out number taken before now is void")


if __name__ == "__main__":
    unittest.main()
