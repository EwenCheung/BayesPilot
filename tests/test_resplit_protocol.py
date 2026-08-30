from __future__ import annotations

import json
from pathlib import Path

from src.eval import harness
from src.r3.flags import Flags


ROOT = Path(__file__).resolve().parents[1]


def test_competition_default_does_not_depend_on_llm_availability() -> None:
    assert not hasattr(Flags(), "llm_attribute")
    assert Flags().llm_extract is False


def test_shared_harness_defaults_to_train_not_public() -> None:
    assert harness.load_world.__defaults__ == (harness.TRAIN_DATASET,)
    assert harness.run.__kwdefaults__["dataset"] == harness.TRAIN_DATASET


def test_fitter_has_no_test_or_public_dataset_path() -> None:
    source = (ROOT / "scripts" / "fit_resplit.py").read_text(encoding="utf-8")
    executable = source.split('if __name__ == "__main__":', 1)[0]
    assert "public_set.jsonl" not in executable
    assert '"test.jsonl"' not in executable


def test_development_evaluator_allows_only_train_and_validation() -> None:
    from scripts.evaluate_resplit import DEVELOPMENT_SPLITS

    assert DEVELOPMENT_SPLITS == {"train", "validation"}


def test_manifest_locks_disjoint_split_targets() -> None:
    data = ROOT / "techjam-conversational-search-main" / "data" / "resplit_60_20_20"
    rows = {
        name: [json.loads(line) for line in (data / f"{name}.jsonl").read_text().splitlines()]
        for name in ("train", "validation", "test")
    }
    targets = {
        name: {row["ground_truth"]["parent_asin"] for row in selected}
        for name, selected in rows.items()
    }
    assert not targets["train"] & targets["validation"]
    assert not targets["train"] & targets["test"]
    assert not targets["validation"] & targets["test"]
