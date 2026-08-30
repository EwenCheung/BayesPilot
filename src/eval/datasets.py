"""Datasets configuration:
    Fitting data: combine/train.jsonl or resplit_60_20_20/train.jsonl
    Testing data: resplit_60_20_20/test.jsonl, freeform_v1/test.jsonl, public_set.jsonl
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

COMBINE_TRAIN = ROOT / "data" / "combine" / "train.jsonl"
COMBINE_VAL = ROOT / "data" / "combine" / "validation.jsonl"

RESPLIT_TRAIN = ROOT / "data" / "resplit_60_20_20" / "train.jsonl"
RESPLIT_VAL = ROOT / "data" / "resplit_60_20_20" / "validation.jsonl"
RESPLIT_TEST = ROOT / "data" / "resplit_60_20_20" / "test.jsonl"

FREEFORM_TEST = ROOT / "data" / "freeform_v1" / "test.jsonl"
FREEFORM_VAL = ROOT / "data" / "freeform_v1" / "validation.jsonl"
FREEFORM_TRAIN = ROOT / "data" / "freeform_v1" / "train.jsonl"

PUBLIC = ROOT / "data" / "public_set.jsonl"

# Default training / fitting dataset
TRAIN = RESPLIT_TRAIN

#: Names that may not appear in fitting code. `tests/test_datasets.py` enforces it.
TEST_ONLY = ("public_set.jsonl", "test.jsonl")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def fitting(corpus: str = "resplit", limit: int | None = None) -> list[dict]:
    """The sessions any fit, sweep or calibration may see (from resplit or combine train)."""
    train_path = COMBINE_TRAIN if corpus == "combine" else RESPLIT_TRAIN
    sessions = load(train_path)
    return sessions[:limit] if limit else sessions


def report(which: str) -> list[dict]:
    """A test set, for reporting only."""
    assert which in ("public", "resplit_test", "freeform_test"), which
    if which == "public":
        return load(PUBLIC)
    if which == "resplit_test":
        return load(RESPLIT_TEST)
    return load(FREEFORM_TEST)
