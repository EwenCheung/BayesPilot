"""Compatibility view of the locked resplit train/validation development boundary.

The former implementation split the public set and was unsafe for tuning. Public and test do not
appear in this module. New code should use ``scripts/fit_resplit.py`` directly.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "techjam-conversational-search-main" / "data" / "resplit_60_20_20"


def _sessions(name: str) -> list[dict]:
    path = DATA / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _development_sessions() -> list[dict]:
    return [*_sessions("train"), *_sessions("validation")]


def targets() -> dict[str, str]:
    return {row["sample_id"]: row["ground_truth"]["parent_asin"] for row in _development_sessions()}


def scenarios() -> dict[str, str]:
    return {row["sample_id"]: row["scenario_type"] for row in _development_sessions()}


def content_hash() -> str:
    split = load()
    payload = json.dumps(
        {"train": split["train"], "validation": split["validation"]},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load() -> dict:
    train = sorted(row["sample_id"] for row in _sessions("train"))
    validation = sorted(row["sample_id"] for row in _sessions("validation"))
    payload = json.dumps({"train": train, "validation": validation}, sort_keys=True)
    return {
        "train": train,
        "validation": validation,
        "hash": hashlib.sha256(payload.encode()).hexdigest()[:16],
    }


def build() -> dict:
    """The split is generated only by scripts/split_train_dev.py."""
    return load()
