"""The immutable 140/60 split (04-merge-plan.md §6).

⚠️ Tune on `train`. Report on `test`. A threshold chosen while looking at `test` has spent it.

Disjoint on sample_id **and** target ASIN. The ASIN constraint is the one that is easy to miss and the
one that matters: two sessions can have different ids and the same hidden product, and a parameter
tuned on one then "generalises" to the other for no good reason.

The manifest is generated once and committed. `content_hash` locks it — if it moves, every held-out
number taken before the move is void, and `tests/test_holdout.py` fails loudly rather than quietly
reporting a better score.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "techjam-conversational-search-main" / "data" / "public_set.jsonl"
MANIFEST = ROOT / "runs" / "holdout.json"
TEST_FRACTION = 0.30
SEED = 20260829


def _sessions() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def targets() -> dict[str, str]:
    return {s["sample_id"]: s["ground_truth"]["parent_asin"] for s in _sessions()}


def scenarios() -> dict[str, str]:
    return {s["sample_id"]: s["scenario_type"] for s in _sessions()}


def content_hash() -> str:
    """Hash of the split itself, so a silently regenerated manifest cannot pass unnoticed."""
    data = json.loads(MANIFEST.read_text())
    payload = json.dumps({"train": sorted(data["train"]), "test": sorted(data["test"])},
                         sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build() -> dict:
    """Generate the split. Run once; the result is committed and never regenerated."""
    sessions = _sessions()
    # Group by target ASIN first: an ASIN is assigned as a unit, so it cannot straddle the split.
    by_asin: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        by_asin[s["ground_truth"]["parent_asin"]].append(s)

    # Stratify by scenario. An ASIN group carries the scenario of its first session; groups are
    # near-always size 1 here, so this is exact in practice and safe when it is not.
    by_scenario: dict[str, list[str]] = defaultdict(list)
    for asin, group in by_asin.items():
        by_scenario[group[0]["scenario_type"]].append(asin)

    rng = random.Random(SEED)
    train_asins: set[str] = set()
    test_asins: set[str] = set()
    for scenario in sorted(by_scenario):
        asins = sorted(by_scenario[scenario])
        rng.shuffle(asins)
        cut = round(len(asins) * TEST_FRACTION)
        test_asins.update(asins[:cut])
        train_asins.update(asins[cut:])

    train = sorted(s["sample_id"] for s in sessions
                   if s["ground_truth"]["parent_asin"] in train_asins)
    test = sorted(s["sample_id"] for s in sessions
                  if s["ground_truth"]["parent_asin"] in test_asins)
    return {"train": train, "test": test, "seed": SEED, "test_fraction": TEST_FRACTION}


def load() -> dict:
    return json.loads(MANIFEST.read_text())


if __name__ == "__main__":
    assert not MANIFEST.exists(), (
        f"{MANIFEST} already exists. Regenerating it voids every held-out number ever reported. "
        "Delete it deliberately if that is really what you mean.")
    split = build()
    MANIFEST.write_text(json.dumps(split, indent=1))
    split["hash"] = content_hash()
    MANIFEST.write_text(json.dumps(split, indent=1))
    print(f"train {len(split['train'])}  test {len(split['test'])}  hash {split['hash']}")
