"""Run any agent through the OFFICIAL evaluator without touching the kit.

The documented workflow is `cp my_agent.py starter/agent.py && python3 -m evaluator.local_evaluator`,
which mutates the kit and makes a reported score unverifiable until you remember to restore it.
We import the evaluator's own `evaluate()` and hand it our agent instance instead.

⚠️ This is legal HERE and illegal in the agent. `evaluator/local_evaluator.py` does
`from starter.agent import Agent` at module scope, so an agent module importing the evaluator is a
circular import and a hard crash (IMPORTANT.md §13.1.1). A harness script sits outside that cycle.
The scoring code that runs is byte-identical to the official one either way.
"""
from __future__ import annotations

import json
import hashlib
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "techjam-conversational-search-main"
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402

CATALOG = ROOT / "assets" / "catalog.jsonl"
SPLIT_DIR = KIT / "data" / "resplit_60_20_20"
TRAIN_DATASET = SPLIT_DIR / "train.jsonl"
VALIDATION_DATASET = SPLIT_DIR / "validation.jsonl"
TEST_DATASET = SPLIT_DIR / "test.jsonl"
REGISTRY = ROOT / "runs" / "registry.jsonl"

_CACHE: dict = {}


def load_world(dataset: str | Path = TRAIN_DATASET) -> tuple[list[dict], set[str], dict, dict]:
    """Parse one explicit development dataset and the catalog once per process.

    Train is intentionally the default. The public path is not defined in this development harness;
    this prevents an old sweep or ablation script from silently tuning against the golden set.
    """
    path = Path(dataset).resolve()
    key = f"world:{path}"
    if key not in _CACHE:
        samples = load_jsonl(path)
        catalog_ids, categories, products = catalog_index(CATALOG)
        _CACHE[key] = (samples, catalog_ids, categories, products)
    return _CACHE[key]


class Rewriter:
    """Base class for the paraphrase stress harness.

    ⚠️ It wraps the AGENT, never the evaluator. The evaluator, the labels and the exact-code hit check
    are untouched; the agent simply hears a reworded version of the same sentence. This is the only
    rules-compliant way to ask 'what happens if the organizer paraphrases the private set?'
    """

    name = "clean"

    def __call__(self, message: str, turn: int) -> str:
        return message


class StressedAgent:
    """Agent proxy that paraphrases the customer's message before the agent sees it."""

    def __init__(self, agent, rewriter: Rewriter) -> None:
        self._agent = agent
        self._rewriter = rewriter

    def reset(self, session_id: str, user_profile: dict) -> None:
        self._agent.reset(session_id, user_profile)

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return self._agent.respond(session_id, self._rewriter(user_message, turn), turn, top_k)

    def __getattr__(self, item):
        return getattr(self._agent, item)


def run(
    agent,
    rewriter: Rewriter | None = None,
    *,
    dataset: str | Path = TRAIN_DATASET,
    sample_limit: int | None = None,
) -> dict:
    """Score one agent. Returns the evaluator's own result dict plus wall-clock."""
    samples, catalog_ids, categories, products = load_world(dataset)
    if sample_limit is not None:
        samples = samples[:sample_limit]
    subject = StressedAgent(agent, rewriter) if rewriter and rewriter.name != "clean" else agent
    t0 = time.time()
    result = evaluate(subject, samples, catalog_ids, categories, products)
    result["elapsed_s"] = round(time.time() - t0, 2)
    result["rewriter"] = rewriter.name if rewriter else "clean"
    return result


def score(result: dict) -> float:
    return result["recommended_technical_score"]


def bootstrap_ci(result: dict, resamples: int = 1000, seed: int = 0) -> tuple[float, float]:
    """95% CI on TechnicalScore by resampling sessions.

    200 sessions is small: a 0.02 gap is one or two sessions changing rank (IMPORTANT.md §13.3).
    No winner is declared without this.
    """
    sessions = result["sessions"]
    n = len(sessions)
    rng = random.Random(seed)
    scores = []
    for _ in range(resamples):
        pick = [sessions[rng.randrange(n)] for _ in range(n)]
        hit = sum(int(s["hit"]) for s in pick) / n
        mrr = statistics.fmean(s["reciprocal_rank"] for s in pick)
        mttc = statistics.fmean(
            s["first_hit_turn"] if s["first_hit_turn"] is not None else 11 for s in pick
        )
        eff = max(0.0, min(1.0, (11.0 - mttc) / 10.0))
        scores.append(0.50 * hit + 0.30 * mrr + 0.20 * eff)
    scores.sort()
    return round(scores[int(0.025 * resamples)], 4), round(scores[int(0.975 * resamples)], 4)


def kit_is_pristine() -> bool:
    """Verify the exact referee inputs while allowing additional released data files.

    A blanket ``git status`` check made the official evaluator look contaminated as soon as the
    separately supplied train/dev files were placed in ``data/``.  The score depends on the guarded
    files in ``kit_manifest.json``; hash those exact inputs instead.
    """
    manifest = json.loads((ROOT / "src" / "eval" / "kit_manifest.json").read_text())
    for relative, expected in manifest.items():
        path = KIT / relative
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return False
    return True


def git_sha() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


def summarize(result: dict) -> dict:
    return {
        "hit_rate_at_10": result["hit_rate_at_10"],
        "mrr": result["mrr"],
        "mttc": result["mttc"],
        "efficiency": result["efficiency"],
        "technical_score": result["recommended_technical_score"],
    }


def register(variant: str, clean: dict, *, paraphrase: dict | None = None,
             ablations: dict | None = None, models: dict | None = None,
             llm_call_failures: int = 0, notes: str = "") -> dict:
    """Append one row to runs/registry.jsonl.

    Per IDEA.md Part IV a run counts only if it carries all four scenario breakdowns, a stressed score,
    the no_spec_phrase ablation, llm_call_failures and a git SHA. We record `kit_pristine` too, because
    a score measured against a modified kit is not a score.
    """
    lo, hi = bootstrap_ci(clean)
    row = {
        "variant": variant,
        "git_sha": git_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kit_pristine": kit_is_pristine(),
        **summarize(clean),
        "scenario": {k: v for k, v in clean["scenario_metrics"].items()},
        "paraphrase": paraphrase or {"clean": score(clean)},
        "ablations": ablations or {},
        "bootstrap": {"lo": lo, "hi": hi},
        "models": models or {},
        "llm_call_failures": llm_call_failures,
        "latency": {"total_s": clean.get("elapsed_s")},
        "notes": notes,
    }
    REGISTRY.parent.mkdir(exist_ok=True)
    with REGISTRY.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    return row
