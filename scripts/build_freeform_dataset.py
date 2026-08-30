"""Build a 1,200/400/800 free-form train/validation/sealed-test corpus."""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "techjam-conversational-search-main"
SOURCE = KIT / "data" / "resplit_60_20_20"
OUTPUT = KIT / "data" / "freeform_v1"
CATALOG = ROOT / "assets" / "catalog.jsonl"
EVALUATOR = KIT / "evaluator" / "local_evaluator.py"
EVALUATOR_SHA256 = "79a5ea06f9a1b8c5036f30efa85dc1f36b8f6b06eb8feb8f545dfa767bc45564"
SEED = 20260830
COUNTS = {
    "train": {"buying": 480, "browsing": 480, "intent_override": 180, "boundary": 60},
    "validation": {"buying": 160, "browsing": 160, "intent_override": 60, "boundary": 20},
    "test": {"buying": 320, "browsing": 320, "intent_override": 120, "boundary": 40},
}

sys.path[:0] = [str(ROOT), str(KIT)]

from evaluator.local_evaluator import (  # noqa: E402
    catalog_index,
    coarse_category,
    initial_message,
    load_jsonl,
    materialize_hidden_fields,
)
from src.eval.freeform import STYLES, VERSION, is_official_grammar, rewrite_message, stable_seed  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(rows: list[dict], split: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row["scenario_type"])].append(row)
    chosen: list[dict] = []
    for scenario, count in COUNTS[split].items():
        candidates = sorted(grouped[scenario], key=lambda row: str(row["sample_id"]))
        random.Random(stable_seed(SEED, split, scenario)).shuffle(candidates)
        if len(candidates) < count:
            raise ValueError(f"{split}/{scenario}: requested {count}, have {len(candidates)}")
        chosen.extend(candidates[:count])
    random.Random(stable_seed(SEED, split, "row-order")).shuffle(chosen)
    return chosen


def main() -> None:
    if sha256(EVALUATOR) != EVALUATOR_SHA256:
        raise SystemExit("official local_evaluator.py hash changed; refusing to build")
    _, categories, products = catalog_index(CATALOG)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "version": VERSION,
        "seed": SEED,
        "evaluator_sha256": EVALUATOR_SHA256,
        "policy": "source-split-preserving; test sealed; every agent-visible turn rewritten",
        "splits": {},
    }
    targets: dict[str, set[str]] = {}

    for split in ("train", "validation", "test"):
        source_path = SOURCE / f"{split}.jsonl"
        selected = select(load_jsonl(source_path), split)
        output_rows: list[dict] = []
        for row in selected:
            target = str(row["ground_truth"]["parent_asin"])
            card, behavior = materialize_hidden_fields(row, products)
            effective = {**row, "intent_card": card, "behavior": behavior}
            canonical = initial_message(effective, coarse_category(categories.get(target, [])), set())
            seed = stable_seed(SEED, split, row["sample_id"])
            style = STYLES[seed % len(STYLES)]
            free_message = rewrite_message(canonical, seed=seed, turn=1, style=style)
            if free_message == canonical or is_official_grammar(free_message):
                raise AssertionError(f"rewrite failed for {row['sample_id']}: {free_message}")
            output_rows.append({
                **row,
                "free_form": {
                    "version": VERSION,
                    "style": style,
                    "seed": seed,
                    "initial_message": free_message,
                    "canonical_initial_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                },
            })

        path = OUTPUT / f"{split}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in output_rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        targets[split] = {str(row["ground_truth"]["parent_asin"]) for row in output_rows}
        coarse_categories = {
            coarse_category(categories.get(str(row["ground_truth"]["parent_asin"]), []))
            for row in output_rows
        }
        manifest["splits"][split] = {
            "path": str(path.relative_to(ROOT)),
            "source_path": str(source_path.relative_to(ROOT)),
            "source_sha256": sha256(source_path),
            "rows": len(output_rows),
            "unique_targets": len(targets[split]),
            "unique_coarse_categories": len(coarse_categories),
            "scenario_counts": dict(sorted(Counter(row["scenario_type"] for row in output_rows).items())),
            "style_counts": dict(sorted(Counter(row["free_form"]["style"] for row in output_rows).items())),
            "official_grammar_matches": sum(
                is_official_grammar(row["free_form"]["initial_message"]) for row in output_rows
            ),
            "sha256": sha256(path),
        }

    pairs = (("train", "validation"), ("train", "test"), ("validation", "test"))
    overlaps = {f"{left}:{right}": sorted(targets[left] & targets[right]) for left, right in pairs}
    if any(overlaps.values()):
        raise AssertionError(f"target leakage: {overlaps}")
    manifest["target_overlaps"] = overlaps
    manifest_path = OUTPUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
