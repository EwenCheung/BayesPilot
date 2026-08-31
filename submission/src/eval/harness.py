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
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
KIT = next(
    (path for path in (
        ROOT / "participation_kit",
        ROOT / "participant_kit",
        ROOT / "techjam-conversational-search-main",
    ) if path.exists()),
    ROOT,
)
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402


def load_env() -> None:
    """`.env` into the process environment, without overriding what is already set.

    ⚠️ Only runner scripts call this. The organizer runs `Agent(catalog)` with no environment at
    all, so anything reaching the agent this way is a LOCAL experiment — the submission is whatever
    `src/copilot/flags.py` says (SUMMARY.md D2).
    """
    import os

    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

CATALOG = ROOT / "data" / "catalog.jsonl"
DATASET = KIT / "data" / "public_set.jsonl"
REGISTRY = ROOT / "runs" / "registry.jsonl"

_CACHE: dict = {}


def load_world() -> tuple[list[dict], set[str], dict, dict]:
    """Parse the catalog and dataset once per process; variants reuse them."""
    if "world" not in _CACHE:
        samples = load_jsonl(DATASET)
        catalog_ids, categories, products = catalog_index(CATALOG)
        _CACHE["world"] = (samples, catalog_ids, categories, products)
    return _CACHE["world"]


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


def run(agent, rewriter: Rewriter | None = None) -> dict:
    """Score one agent. Returns the evaluator's own result dict plus wall-clock."""
    samples, catalog_ids, categories, products = load_world()
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


def _session_arrays(result: dict):
    import numpy as np

    sessions = result["sessions"]
    hit = np.fromiter((float(s["hit"]) for s in sessions), float, len(sessions))
    rr = np.fromiter((float(s["reciprocal_rank"]) for s in sessions), float, len(sessions))
    ttc = np.fromiter(
        ((s["first_hit_turn"] if s["first_hit_turn"] is not None else 11) for s in sessions),
        float, len(sessions))
    return hit, rr, ttc


def paired_bootstrap_ci(before: list[dict], after: list[dict],
                        resamples: int = 1000, seed: int = 0) -> tuple[float, float]:
    """95% CI on `after - before`, resampling the same sessions in both configurations."""
    import numpy as np

    assert len(before) == len(after) and before, "paired bootstrap needs matching runs"
    pairs = [(_session_arrays(b), _session_arrays(a)) for b, a in zip(before, after)]
    n = len(pairs[0][0][0])
    assert all(len(x[0]) == n for pair in pairs for x in pair), \
        "runs must cover the same sessions"

    def technical(hit, rr, ttc, idx):
        eff = np.clip((11.0 - ttc[idx].mean(axis=1)) / 10.0, 0.0, 1.0)
        return 0.50 * hit[idx].mean(axis=1) + 0.30 * rr[idx].mean(axis=1) + 0.20 * eff

    idx = np.random.default_rng(seed).integers(0, n, size=(resamples, n))
    delta = np.zeros(resamples)
    for (b_hit, b_rr, b_ttc), (a_hit, a_rr, a_ttc) in pairs:
        delta += technical(a_hit, a_rr, a_ttc, idx) - technical(b_hit, b_rr, b_ttc, idx)
    delta /= len(pairs)
    lo, hi = np.percentile(delta, [2.5, 97.5])
    return round(float(lo), 4), round(float(hi), 4)


MANIFEST = ROOT / "src" / "eval" / "kit_manifest.json"
GUARDED = ("evaluator/local_evaluator.py", "data/public_set.jsonl", "starter/agent.py",
           "docs/evaluation_config.json", "docs/agent_api_contract.json")


def manifest() -> dict:
    import hashlib
    res = {}
    for name in GUARDED:
        target = (KIT / name) if (KIT / name).exists() else (ROOT / name)
        if target.exists():
            res[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return res


def ensure_manifest() -> None:
    if not MANIFEST.exists():
        MANIFEST.write_text(json.dumps(manifest(), indent=2))


def verify_kit() -> None:
    """Raise rather than record a run against a drifted kit."""
    if not MANIFEST.exists():
        return
    expected = json.loads(MANIFEST.read_text())
    actual = manifest()
    drift = {n: (expected[n], actual[n]) for n in expected if n in actual and expected[n] != actual[n]}
    if drift:
        raise SystemExit(f"kit drifted from pristine, refusing to record a run: {drift}")


def kit_is_pristine() -> bool:
    """A reported score is worthless if the kit drifted. Checked before every registry row."""
    if not MANIFEST.exists():
        return True
    expected = json.loads(MANIFEST.read_text())
    actual = manifest()
    return all(actual.get(k) == expected[k] for k in expected if (KIT / k).exists() or (ROOT / k).exists())


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
