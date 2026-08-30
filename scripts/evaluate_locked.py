"""Evaluate the frozen resplit configuration, with an explicit gate for the golden set.

This script performs no fitting or selection.  It verifies the training/validation hashes recorded by
``fit_resplit.py``, evaluates the locked test split first, and reads the public golden set only when
``--acknowledge-golden-final`` is supplied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "techjam-conversational-search-main"
DATA = KIT / "data"
SPLIT = DATA / "resplit_60_20_20"
CATALOG = ROOT / "assets" / "catalog.jsonl"
LOCK = ROOT / "runs" / "r3_resplit_locked.json"
OUTPUT = ROOT / "runs" / "r3_locked_final.json"

os.environ["R3_OFFLINE"] = "1"
sys.path[:0] = [str(ROOT), str(KIT)]

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from src.eval.harness import bootstrap_ci  # noqa: E402
from src.r3.agent import Agent  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _evaluate(path: Path, config: dict[str, float], world: tuple[set[str], dict, dict]) -> dict:
    catalog_ids, categories, products = world
    agent = Agent(CATALOG)
    for name, value in config.items():
        setattr(agent.flags, name, value)
    agent.flags.llm_attribute = False
    agent.flags.llm_extract = False
    started = time.time()
    result = evaluate(agent, load_jsonl(path), catalog_ids, categories, products)
    return {
        "sample_count": result["sample_count"],
        "hit_rate_at_10": result["hit_rate_at_10"],
        "mrr": result["mrr"],
        "mttc": result["mttc"],
        "efficiency": result["efficiency"],
        "technical_score": result["recommended_technical_score"],
        "bootstrap_95_ci": bootstrap_ci(result, resamples=1000, seed=20260830),
        "scenario_metrics": result["scenario_metrics"],
        "token_usage": result["reported_token_usage"],
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--acknowledge-golden-final",
        action="store_true",
        help="after the locked test run, also spend the public golden evaluation",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    guarded = {
        "train": SPLIT / "train.jsonl",
        "validation": SPLIT / "validation.jsonl",
    }
    for name, path in guarded.items():
        if _sha256(path) != lock["dataset_hashes"][name]:
            raise RuntimeError(f"{name} changed after fitting; refusing final evaluation")

    config = lock["selected_config"]
    world = catalog_index(CATALOG)
    output = {
        "lock_sha256": _sha256(LOCK),
        "selected_name": lock["selected_name"],
        "selected_config": config,
        "test": _evaluate(SPLIT / "test.jsonl", config, world),
    }
    print(json.dumps({"test": output["test"]}, sort_keys=True), flush=True)

    if args.acknowledge_golden_final:
        output["public_golden"] = _evaluate(DATA / "public_set.jsonl", config, world)
        print(json.dumps({"public_golden": output["public_golden"]}, sort_keys=True), flush=True)

    destination = args.output if args.output.is_absolute() else ROOT / args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"written: {destination}", flush=True)


if __name__ == "__main__":
    main()
