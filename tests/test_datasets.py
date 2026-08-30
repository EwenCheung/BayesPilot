"""The train/dev/test contract: fit on train.jsonl, report on dev and public, never the reverse.

The project had already recorded two leakage audits before this rule existed. This test is the
mechanical version of the rule, so it is a build failure rather than a habit.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import datasets  # noqa: E402

# Code whose job is to CHOOSE a value. None of it may read an evaluation set.
# ⚠️ `scripts/fit_policy.py` is deliberately NOT here: it is R3's legacy fit, which ran against a
# split of `public_set.jsonl` before this rule existed. It is superseded by `scripts/fit_r4.py` and
# kept only so R3's published constants remain reproducible. Do not fit with it.
FITTING_CODE = ("src/r4", "scripts/fit_r4.py")
#: Also forbidden in fitting code — `holdout` splits the public 200, which is an evaluation set.
FORBIDDEN_MODULES = ("holdout",)


class TestDatasetContract(unittest.TestCase):
    def test_all_three_exist_with_the_expected_sizes(self) -> None:
        self.assertEqual(len(datasets.load(datasets.TRAIN)), 12000)
        self.assertEqual(len(datasets.load(datasets.DEV)), 2000)
        self.assertEqual(len(datasets.load(datasets.PUBLIC)), 200)

    def test_target_asins_are_mutually_disjoint(self) -> None:
        """The property that makes the three sets meaningfully different measurements."""
        def asins(path): return {s["ground_truth"]["parent_asin"] for s in datasets.load(path)}
        train, dev, public = asins(datasets.TRAIN), asins(datasets.DEV), asins(datasets.PUBLIC)
        self.assertEqual(train & dev, set())
        self.assertEqual(train & public, set())
        self.assertEqual(dev & public, set())

    def test_scenario_mix_is_identical_across_the_three(self) -> None:
        """A number must move because the agent generalised, not because the mix changed."""
        import collections
        for path in (datasets.TRAIN, datasets.DEV, datasets.PUBLIC):
            counts = collections.Counter(s["scenario_type"] for s in datasets.load(path))
            total = sum(counts.values())
            for scenario, expected in (("buying", 0.40), ("browsing", 0.40),
                                       ("intent_override", 0.15), ("boundary", 0.05)):
                self.assertAlmostEqual(counts[scenario] / total, expected, places=2,
                                       msg=f"{path.name}/{scenario}")

    def test_fitting_code_never_names_an_evaluation_set(self) -> None:
        """⚠️ The rule that matters. A fit that can see dev has already spent it."""
        for target in FITTING_CODE:
            path = ROOT / target
            files = sorted(path.rglob("*.py")) if path.is_dir() else ([path] if path.exists() else [])
            for file in files:
                text = file.read_text(encoding="utf-8")
                for forbidden in datasets.TEST_ONLY + FORBIDDEN_MODULES:
                    self.assertNotIn(forbidden, text,
                                     f"{file.relative_to(ROOT)} names {forbidden}; fit on train.jsonl")
                for node in ast.walk(ast.parse(text)):
                    if isinstance(node, ast.Attribute) and node.attr in ("DEV", "PUBLIC"):
                        self.fail(f"{file.relative_to(ROOT)} reaches for datasets.{node.attr}")

    def test_fitting_returns_train_only(self) -> None:
        train_ids = {s["sample_id"] for s in datasets.load(datasets.TRAIN)}
        self.assertTrue({s["sample_id"] for s in datasets.fitting(50)} <= train_ids)
        self.assertEqual(len(datasets.fitting(50)), 50)


if __name__ == "__main__":
    unittest.main()
