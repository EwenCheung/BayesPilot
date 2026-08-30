"""Evaluate R3 on the generated 60/20/20 data split.

Examples:

    python3 scripts/evaluate_resplit.py --mode offline --splits train,validation
    python3 scripts/evaluate_resplit.py --mode full-llm --splits train --sample-per-scenario 5

For full-LLM mode, export the endpoint credentials before running.  The script never loads or prints
secrets itself.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "techjam-conversational-search-main"
SPLIT_DIR = KIT / "data" / "resplit_60_20_20"
CATALOG = ROOT / "assets" / "catalog.jsonl"
DEVELOPMENT_SPLITS = frozenset({"train", "validation"})
sys.path[:0] = [str(ROOT), str(KIT)]

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from src.eval.harness import bootstrap_ci  # noqa: E402
from src.r3.agent import Agent  # noqa: E402


def _sample(rows: list[dict], per_scenario: int, seed: int) -> list[dict]:
    if per_scenario <= 0:
        return rows
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row["scenario_type"])].append(row)
    rng = random.Random(seed)
    selected = []
    for scenario in sorted(grouped):
        choices = list(grouped[scenario])
        rng.shuffle(choices)
        selected.extend(choices[:per_scenario])
    return sorted(selected, key=lambda row: str(row["sample_id"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "full-llm"), required=True)
    parser.add_argument("--splits", default="validation")
    parser.add_argument("--sample-per-scenario", type=int, default=0)
    parser.add_argument("--r3-flags", default="")
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.mode == "offline":
        os.environ["R3_OFFLINE"] = "1"
    else:
        os.environ.pop("R3_OFFLINE", None)
    if args.r3_flags:
        os.environ["R3_FLAGS"] = args.r3_flags

    catalog_ids, categories, products = catalog_index(CATALOG)
    output = {"mode": args.mode, "sample_per_scenario": args.sample_per_scenario,
              "r3_flags": args.r3_flags, "splits": {}}
    requested = [value.strip() for value in args.splits.split(",") if value.strip()]
    forbidden = sorted(set(requested) - DEVELOPMENT_SPLITS)
    if forbidden:
        raise SystemExit(
            f"development evaluator permits only train/validation, not {forbidden}; "
            "use scripts/evaluate_locked.py for final test/public evaluation"
        )
    for name in requested:
        rows = _sample(load_jsonl(SPLIT_DIR / f"{name}.jsonl"), args.sample_per_scenario, args.seed)
        agent = Agent(CATALOG)
        agent.flags.llm_attribute = args.mode == "full-llm"
        agent.flags.llm_extract = False
        started = time.time()
        result = evaluate(agent, rows, catalog_ids, categories, products)
        summary = {key: value for key, value in result.items() if key != "sessions"}
        summary["bootstrap_95_ci"] = bootstrap_ci(result, resamples=1000, seed=args.seed)
        summary["elapsed_s"] = round(time.time() - started, 2)
        summary["llm"] = agent.llm.report() if agent.llm is not None else {
            "calls": 0, "cache_hits": 0, "failures": 0,
            "prompt_tokens": 0, "completion_tokens": 0,
        }
        output["splits"][name] = summary
        print(json.dumps({"split": name, **summary}, sort_keys=True), flush=True)

    if args.output:
        path = Path(args.output)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"written: {path}")


if __name__ == "__main__":
    main()
