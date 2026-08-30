"""Merge the released train/dev sessions and make a locked 60/20/20 split.

The source files are never modified.  Splits are stratified by scenario and grouped by target ASIN,
so the same product can never appear on both sides if a future dataset contains repeated targets.

Run from the repository root:

    python3 scripts/split_train_dev.py
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "techjam-conversational-search-main" / "data"
SOURCES = (DATA / "train.jsonl", DATA / "dev.jsonl")
OUTPUT = DATA / "resplit_60_20_20"
SEED = 20260830
RATIOS = {"train": 0.60, "validation": 0.20, "test": 0.20}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(paths: tuple[Path, ...] = SOURCES) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


def split_rows(rows: list[dict], seed: int = SEED) -> dict[str, list[dict]]:
    """Return exact scenario-stratified splits, keeping each target in only one split."""
    sample_ids = [str(row["sample_id"]) for row in rows]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("sample_id values must be unique before splitting")

    by_target: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_target[str(row["ground_truth"]["parent_asin"])].append(row)

    by_scenario: dict[str, list[tuple[str, list[dict]]]] = defaultdict(list)
    for target, group in by_target.items():
        scenarios = {str(row["scenario_type"]) for row in group}
        if len(scenarios) != 1:
            raise ValueError(f"target {target} occurs under multiple scenarios: {sorted(scenarios)}")
        by_scenario[next(iter(scenarios))].append((target, group))

    result: dict[str, list[dict]] = {name: [] for name in RATIOS}
    rng = random.Random(seed)
    for scenario in sorted(by_scenario):
        groups = sorted(by_scenario[scenario], key=lambda item: item[0])
        rng.shuffle(groups)
        total_rows = sum(len(group) for _, group in groups)
        if any(len(group) != 1 for _, group in groups):
            raise ValueError(
                "exact 60/20/20 row counts require unique targets; repeated targets were found"
            )
        train_end = round(total_rows * RATIOS["train"])
        validation_end = train_end + round(total_rows * RATIOS["validation"])
        partitions = {
            "train": groups[:train_end],
            "validation": groups[train_end:validation_end],
            "test": groups[validation_end:],
        }
        for name, selected in partitions.items():
            for _, group in selected:
                result[name].extend(group)

    for name in result:
        result[name].sort(key=lambda row: str(row["sample_id"]))
    return result


def _counts(rows: list[dict]) -> dict[str, int]:
    return dict(sorted(Counter(str(row["scenario_type"]) for row in rows).items()))


def _assert_disjoint(splits: dict[str, list[dict]]) -> None:
    names = list(splits)
    for i, left in enumerate(names):
        left_ids = {str(row["sample_id"]) for row in splits[left]}
        left_targets = {str(row["ground_truth"]["parent_asin"]) for row in splits[left]}
        for right in names[i + 1:]:
            right_ids = {str(row["sample_id"]) for row in splits[right]}
            right_targets = {str(row["ground_truth"]["parent_asin"]) for row in splits[right]}
            if left_ids & right_ids:
                raise AssertionError(f"sample leakage between {left} and {right}")
            if left_targets & right_targets:
                raise AssertionError(f"target leakage between {left} and {right}")


def main() -> None:
    rows = _load()
    splits = split_rows(rows)
    _assert_disjoint(splits)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, dict] = {}
    for name, selected in splits.items():
        path = OUTPUT / f"{name}.jsonl"
        payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in selected)
        path.write_text(payload, encoding="utf-8")
        outputs[name] = {
            "path": str(path.relative_to(ROOT)),
            "rows": len(selected),
            "scenario_counts": _counts(selected),
            "sha256": _sha256(path),
        }

    manifest = {
        "seed": SEED,
        "ratios": RATIOS,
        "source_rows": len(rows),
        "source_scenario_counts": _counts(rows),
        "sources": {
            str(path.relative_to(ROOT)): {"sha256": _sha256(path)} for path in SOURCES
        },
        "splits": outputs,
    }
    manifest_path = OUTPUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
