"""The three datasets, and the rule about which one you are allowed to fit on.

    train.jsonl   12,000 sessions   ← FIT HERE. Everything: constants, thresholds, calibrators.
    dev.jsonl      2,000 sessions   ← test only. Read to report, never to choose.
    public_set     200 sessions     ← test only. The official set; read least of all.

Target ASINs are mutually disjoint across all three (verified by `tests/test_datasets.py`), and all
three carry the identical 40/40/15/5 scenario mix, so a number moves between them only because the
agent generalised — not because the mix changed.

⚠️ **This supersedes `devsplit.py`, which carved `dev.jsonl` into 1200/800 and fitted on the first
half.** Splitting an evaluation set does not make it a training set; it spends it either way. That
module is gone and `train.jsonl` is the fitting set.

⚠️ **A parameter chosen while looking at `dev` or `public` is contaminated even if it is never
committed** — the choice was informed. When that happens, say so and re-fit here rather than quietly
keeping the value.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TRAIN = ROOT / "data" / "train.jsonl"
DEV = ROOT / "data" / "dev.jsonl"
PUBLIC = ROOT / "techjam-conversational-search-main" / "data" / "public_set.jsonl"

#: Names that may not appear in fitting code. `tests/test_datasets.py` enforces it.
TEST_ONLY = ("dev.jsonl", "public_set.jsonl")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def fitting(limit: int | None = None) -> list[dict]:
    """The only sessions any fit, sweep or calibration may see.

    `limit` takes a deterministic prefix for a cheap sweep — 12,000 sessions is ~6 minutes a run, and
    a sweep over eight values does not need all of them. Confirm the winner on the full set.
    """
    sessions = load(TRAIN)
    return sessions[:limit] if limit else sessions


def report(which: str) -> list[dict]:
    """A test set, for reporting only. Named explicitly so the call site is auditable."""
    assert which in ("dev", "public"), which
    return load(DEV if which == "dev" else PUBLIC)
