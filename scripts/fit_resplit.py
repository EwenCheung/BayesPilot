"""Select a locked R3 configuration without reading test or public labels.

Protocol:

* fit candidate configurations on ``resplit_60_20_20/train.jsonl``;
* carry only the three best training candidates (plus the baseline) to validation;
* select on ``validation.jsonl`` with a conservative improvement threshold;
* write the immutable configuration and dataset hashes to ``runs/r3_resplit_locked.json``.

This script deliberately has no test/public path or command-line dataset override.  Final evaluation
is handled by ``scripts/evaluate_locked.py`` after this artifact has been written.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "techjam-conversational-search-main"
DATA = KIT / "data" / "resplit_60_20_20"
TRAIN = DATA / "train.jsonl"
VALIDATION = DATA / "validation.jsonl"
CATALOG = ROOT / "assets" / "catalog.jsonl"
OUTPUT = ROOT / "runs" / "r3_resplit_locked.json"
MIN_VALIDATION_GAIN = 0.002

os.environ["R3_OFFLINE"] = "1"
sys.path[:0] = [str(ROOT), str(KIT)]

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from src.r3.agent import Agent  # noqa: E402
from src.r3.flags import Flags  # noqa: E402


# A small, declared one-factor grid limits validation adaptivity.  It covers every fitted clean-path
# constant whose present value came from the legacy public-200 development cycle.
CANDIDATES: tuple[tuple[str, dict[str, float]], ...] = (
    ("neutral", {
        "exact_gain": 3.2,
        "prior_weight": 0.18,
        "v_continue": 0.90,
        "stall_decay": 0.20,
        "stall_decay_clean": 0.80,
        "temperature": 2.0,
        "tau_mass": 0.90,
    }),
    ("prior_010", {"prior_weight": 0.10}),
    ("prior_026", {"prior_weight": 0.26}),
    ("prior_040", {"prior_weight": 0.40}),
    ("gain_240", {"exact_gain": 2.40}),
    ("gain_400", {"exact_gain": 4.00}),
    ("patience_075", {"v_continue": 0.75}),
    ("patience_095", {"v_continue": 0.95}),
    ("mass_085", {"tau_mass": 0.85}),
    ("mass_096", {"tau_mass": 0.96}),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolved_candidates() -> list[tuple[str, dict[str, float]]]:
    neutral = dict(CANDIDATES[0][1])
    return [(name, neutral | overrides) for name, overrides in CANDIDATES]


def _set_flags(agent: Agent, config: dict[str, float]) -> None:
    defaults = Flags()
    for field in dataclasses.fields(defaults):
        setattr(agent.flags, field.name, getattr(defaults, field.name))
    for name, value in config.items():
        setattr(agent.flags, name, value)
    agent.flags.llm_extract = False
    agent.sessions.clear()
    agent._last_asked.clear()
    agent._stalls.clear()


def _score(agent: Agent, rows: list[dict], world: tuple[set[str], dict, dict]) -> dict:
    catalog_ids, categories, products = world
    started = time.time()
    result = evaluate(agent, rows, catalog_ids, categories, products)
    return {
        "sample_count": result["sample_count"],
        "hit_rate_at_10": result["hit_rate_at_10"],
        "mrr": result["mrr"],
        "mttc": result["mttc"],
        "technical_score": result["recommended_technical_score"],
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> None:
    train = load_jsonl(TRAIN)
    validation = load_jsonl(VALIDATION)
    world = catalog_index(CATALOG)
    agent = Agent(CATALOG)

    configs = dict(_resolved_candidates())
    train_results: dict[str, dict] = {}
    for index, (name, config) in enumerate(configs.items(), 1):
        _set_flags(agent, config)
        result = _score(agent, train, world)
        train_results[name] = result
        print(f"train {index:02d}/{len(configs)} {name:<14} {result['technical_score']:.6f}", flush=True)

    top_train = sorted(
        configs,
        key=lambda name: (-train_results[name]["technical_score"], name),
    )[:3]
    finalists = list(dict.fromkeys(["neutral", *top_train]))

    validation_results: dict[str, dict] = {}
    for index, name in enumerate(finalists, 1):
        _set_flags(agent, configs[name])
        result = _score(agent, validation, world)
        validation_results[name] = result
        print(
            f"validation {index:02d}/{len(finalists)} {name:<14} "
            f"{result['technical_score']:.6f}",
            flush=True,
        )

    best = max(
        finalists,
        key=lambda name: (
            validation_results[name]["technical_score"],
            train_results[name]["technical_score"],
            name == "neutral",
        ),
    )
    neutral_score = validation_results["neutral"]["technical_score"]
    if validation_results[best]["technical_score"] < neutral_score + MIN_VALIDATION_GAIN:
        best = "neutral"

    artifact = {
        "protocol": "train-fit_validation-select_test-and-public-unread",
        "minimum_validation_gain": MIN_VALIDATION_GAIN,
        "dataset_hashes": {
            "train": _sha256(TRAIN),
            "validation": _sha256(VALIDATION),
        },
        "candidate_grid": configs,
        "train_results": train_results,
        "validation_finalists": finalists,
        "validation_results": validation_results,
        "selected_name": best,
        "selected_config": configs[best],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"locked {best}: {json.dumps(configs[best], sort_keys=True)}", flush=True)
    print(f"written: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
