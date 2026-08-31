"""Datasets configuration:
    Fitting data: generated_template_set/train.jsonl
    Testing data: generated_template_set/test.jsonl, freeform_set/test.jsonl, public_set.jsonl
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

GENERATED_TEMPLATE_TRAIN = ROOT / "data" / "generated_template_set" / "train.jsonl"
GENERATED_TEMPLATE_VAL = ROOT / "data" / "generated_template_set" / "validation.jsonl"
GENERATED_TEMPLATE_TEST = ROOT / "data" / "generated_template_set" / "test.jsonl"

FREEFORM_TEST = ROOT / "data" / "freeform_set" / "test.jsonl"
FREEFORM_VAL = ROOT / "data" / "freeform_set" / "validation.jsonl"
FREEFORM_TRAIN = ROOT / "data" / "freeform_set" / "train.jsonl"

PUBLIC = ROOT / "data" / "public_set.jsonl"

# Default training / fitting dataset
TRAIN = GENERATED_TEMPLATE_TRAIN

#: Names that may not appear in fitting code. `tests/test_datasets.py` enforces it.
TEST_ONLY = ("public_set.jsonl", "test.jsonl")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def fitting(limit: int | None = None) -> list[dict]:
    """The generated-template sessions any fit, sweep, or calibration may see."""
    sessions = load(GENERATED_TEMPLATE_TRAIN)
    return sessions[:limit] if limit else sessions


def report(which: str) -> list[dict]:
    """A test set, for reporting only."""
    assert which in ("public", "generated_template_test", "freeform_test"), which
    if which == "public":
        return load(PUBLIC)
    if which == "generated_template_test":
        return load(GENERATED_TEMPLATE_TEST)
    return load(FREEFORM_TEST)
