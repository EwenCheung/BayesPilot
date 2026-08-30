"""Evaluate the free-form corpus with the byte-identical official local evaluator."""
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
DATA = KIT / "data" / "freeform_v1"
CATALOG = ROOT / "assets" / "catalog.jsonl"
EVALUATOR = KIT / "evaluator" / "local_evaluator.py"
EVALUATOR_SHA256 = "79a5ea06f9a1b8c5036f30efa85dc1f36b8f6b06eb8feb8f545dfa767bc45564"
sys.path[:0] = [str(ROOT), str(KIT)]

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from src.eval.freeform import FreeFormDatasetAgent  # noqa: E402
from src.eval.harness import bootstrap_ci  # noqa: E402
from src.r3.agent import Agent  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "always-router"), required=True)
    parser.add_argument("--splits", default="validation")
    parser.add_argument("--acknowledge-sealed-test", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    actual_hash = hashlib.sha256(EVALUATOR.read_bytes()).hexdigest()
    if actual_hash != EVALUATOR_SHA256:
        raise SystemExit("official local_evaluator.py hash changed; score rejected")
    requested = [name.strip() for name in args.splits.split(",") if name.strip()]
    unknown = sorted(set(requested) - {"train", "validation", "test"})
    if unknown:
        raise SystemExit(f"unknown free-form splits: {unknown}")
    if "test" in requested and not args.acknowledge_sealed_test:
        raise SystemExit("test is sealed; add --acknowledge-sealed-test only for a final evaluation")

    if args.mode == "offline":
        os.environ["R3_OFFLINE"] = "1"
    else:
        os.environ.pop("R3_OFFLINE", None)

    catalog_ids, categories, products = catalog_index(CATALOG)
    output = {
        "mode": args.mode,
        "evaluator_sha256": actual_hash,
        "message_adapter": "freeform-v1",
        "splits": {},
    }
    for split in requested:
        rows = load_jsonl(DATA / f"{split}.jsonl")
        agent = Agent(CATALOG)
        subject = FreeFormDatasetAgent(agent, rows)
        started = time.time()
        result = evaluate(subject, rows, catalog_ids, categories, products)
        summary = {key: value for key, value in result.items() if key != "sessions"}
        summary["bootstrap_95_ci"] = bootstrap_ci(result, resamples=1000, seed=20260830)
        summary["elapsed_s"] = round(time.time() - started, 2)
        summary["llm"] = agent.llm.report() if agent.llm is not None else {
            "calls": 0,
            "cache_hits": 0,
            "failures": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
        output["splits"][split] = summary
        print(json.dumps({"split": split, **summary}, sort_keys=True), flush=True)

    if args.output:
        path = Path(args.output)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"written: {path}")


if __name__ == "__main__":
    main()

