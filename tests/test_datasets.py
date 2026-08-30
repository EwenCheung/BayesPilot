"""The datasets contract: fit on train data (combine/resplit), test on resplit/test, freeform/test, and public_set."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import datasets  # noqa: E402

FITTING_CODE = ("src/r4", "scripts/fit_r4.py")
FORBIDDEN_MODULES = ("holdout",)


class TestDatasetContract(unittest.TestCase):
    def test_datasets_exist_and_load(self) -> None:
        self.assertGreater(len(datasets.load(datasets.COMBINE_TRAIN)), 0)
        self.assertGreater(len(datasets.load(datasets.RESPLIT_TRAIN)), 0)
        self.assertGreater(len(datasets.load(datasets.RESPLIT_TEST)), 0)
        self.assertGreater(len(datasets.load(datasets.FREEFORM_TEST)), 0)
        self.assertEqual(len(datasets.load(datasets.PUBLIC)), 200)

    def test_fitting_code_never_names_an_evaluation_set(self) -> None:
        """Fitting code should not reference test datasets."""
        for target in FITTING_CODE:
            path = ROOT / target
            files = sorted(path.rglob("*.py")) if path.is_dir() else ([path] if path.exists() else [])
            for file in files:
                text = file.read_text(encoding="utf-8")
                for forbidden in datasets.TEST_ONLY + FORBIDDEN_MODULES:
                    self.assertNotIn(forbidden, text,
                                     f"{file.relative_to(ROOT)} names {forbidden}; fit on train.jsonl")

    def test_fitting_returns_train_only(self) -> None:
        train_ids = {s["sample_id"] for s in datasets.load(datasets.TRAIN)}
        self.assertTrue({s["sample_id"] for s in datasets.fitting("resplit", 50)} <= train_ids)
        self.assertEqual(len(datasets.fitting("resplit", 50)), 50)


if __name__ == "__main__":
    unittest.main()

