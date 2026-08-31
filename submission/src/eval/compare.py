"""Spec 3.10 — the run registry, the scenario breakdown, and the bootstrap CI.

A 0.02 gap on 200 sessions can be one or two sessions changing rank, so no
result is reported without a resampled interval.
"""
from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "runs" / "registry.jsonl"
MAX_TURNS = 11

REFERENCE = {
    "shipped BM25 starter": 0.10671,
    "popularity + category only": 0.71334,
    "public PR#1 trick": 0.750401,
    "ByteMe day-0 run": 0.78576,
    "blended paraphrase-proof floor": 0.826,
    "prototype agent_best_0.9607": 0.96070,
    "theoretical maximum": 0.9922,
}


def technical_score(sessions: list[dict]) -> float:
    hit = sum(1 for s in sessions if s["hit"]) / len(sessions)
    mrr = sum(s["reciprocal_rank"] for s in sessions) / len(sessions)
    mttc = sum(s["first_hit_turn"] or MAX_TURNS for s in sessions) / len(sessions)
    efficiency = max(0.0, min(1.0, (11.0 - mttc) / 10.0))
    return 0.50 * hit + 0.30 * mrr + 0.20 * efficiency


def bootstrap(sessions: list[dict], resamples: int = 1000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    scores = []
    for _ in range(resamples):
        sample = [sessions[rng.randrange(len(sessions))] for _ in range(len(sessions))]
        scores.append(technical_score(sample))
    scores.sort()
    return round(scores[int(0.025 * resamples)], 4), round(scores[int(0.975 * resamples)], 4)


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def row(result: dict, extra: dict | None = None) -> dict:
    sessions = result["sessions"]
    low, high = bootstrap(sessions)
    record = {
        "variant": result.get("variant", "r1"),
        "git_sha": git_sha(),
        "hit_rate_at_10": result["hit_rate_at_10"],
        "mrr": result["mrr"],
        "mttc": result["mttc"],
        "efficiency": result["efficiency"],
        "technical_score": result["recommended_technical_score"],
        "ci95": [low, high],
        "scenario": {
            name: {"n": metrics["sample_count"], "hit": metrics["hit_rate_at_10"],
                   "mrr": metrics["mrr"], "mttc": metrics["mttc"]}
            for name, metrics in result["scenario_metrics"].items()
        },
        "env": result.get("env", {}),
        "wall_clock_s": result.get("wall_clock_s"),
        "tokens": result.get("reported_token_usage", {}),
        "llm": result.get("llm", {}),
    }
    record.update(extra or {})
    return record


def append(record: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
