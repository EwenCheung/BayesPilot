"""Re-fit R4's constants on `train.jsonl`. No evaluation set is opened here.

R4 inherited six fitted constants from R3, and every one of them was fitted on a 120-session split
of the official 200 — a set we now know is saturated (R4 scores Hit 1.0000 / MRR 1.0000 there, so it
can no longer discriminate anything). One of the six, `stall_decay_clean`, turned out to be worth
nothing once the bug it was compensating for was fixed (D11). This re-derives all six on 12,000
sessions with disjoint targets.

Staged, not a grid, and in the same order as `scripts/fit_policy.py`: the prior's units dominate
everything downstream, so it is fitted first and the policy is fitted underneath it. Stage 2 is
coordinate descent rather than R3's 2x3x3 product — 18 objectives is 12 minutes here and the
parameters were measured as near-separable.

    python3 scripts/fit_r4.py [n_sessions]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["R3_OFFLINE"] = "1"                        # fit on the offline path (R3 D22)

from src.eval import datasets, harness, race          # noqa: E402  harness puts the kit on sys.path
from evaluator.local_evaluator import evaluate        # noqa: E402  must follow harness
from src.eval.stress import ParaphraseRewriter        # noqa: E402

_WORLD = None


def score_on(samples, stress=0, **overrides):
    global _WORLD
    if _WORLD is None:
        harness.DATASET = datasets.TRAIN
        _WORLD = harness.load_world()
    _, cid, cats, prods = _WORLD
    os.environ["R4_FLAGS"] = "exclude_shipped"
    agent = measure.build()
    for key, value in overrides.items():
        setattr(agent.flags, key, value)
    subject = harness.StressedAgent(agent, ParaphraseRewriter(stress)) if stress else agent
    return harness.score(evaluate(subject, samples, cid, cats, prods))


def objective(samples, **kw):
    """Clean, L2 and L3 weighted equally — R3's objective, kept identical so the re-fit is a
    like-for-like replacement rather than a change of target as well as a change of data."""
    return (score_on(samples, 0, **kw) + score_on(samples, 2, **kw) + score_on(samples, 3, **kw)) / 3


def sweep(name, values, samples, chosen):
    best = None
    for value in values:
        obj = objective(samples, **dict(chosen, **{name: value}))
        print(f"  {name} {value:>6} | obj {obj:.4f}", flush=True)
        if best is None or obj > best[0]:
            best = (obj, value)
    chosen[name] = best[1]
    print(f"  -> {name} = {best[1]}  (obj {best[0]:.4f})\n", flush=True)
    return chosen


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2500
    samples = datasets.fitting(n)
    print(f"fitting R4 on train.jsonl[:{n}] — dev and public are not opened\n")

    from src.copilot.flags import Flags
    inherited = {k: getattr(Flags(), k) for k in
                 ("prior_weight", "v_continue", "stall_decay", "stall_decay_clean",
                  "exact_gain", "tau_mass")}
    print(f"inherited from R3 (fitted on the official 200): {inherited}")
    print(f"baseline obj {objective(samples):.4f}\n", flush=True)

    chosen: dict = {}
    print("stage 1 — prior weight (its units dominate everything else)")
    sweep("prior_weight", (0.10, 0.18, 0.26, 0.40), samples, chosen)

    print("stage 2 — patience, by coordinate descent")
    sweep("v_continue", (0.75, 0.90, 0.97), samples, chosen)
    sweep("stall_decay", (0.2, 0.35, 0.6), samples, chosen)
    sweep("stall_decay_clean", (0.4, 0.6, 0.8), samples, chosen)

    print("stage 3 — evidence gain and pool mass")
    sweep("exact_gain", (2.0, 3.2, 4.5), samples, chosen)
    sweep("tau_mass", (0.85, 0.90, 0.96), samples, chosen)

    print(f"FITTED ON TRAIN: {chosen}")
    print(f"  inherited obj {objective(samples):.4f}   fitted obj {objective(samples, **chosen):.4f}")
    for level in (0, 2, 3):
        print(f"  L{level}: inherited {score_on(samples, level):.4f}   "
              f"fitted {score_on(samples, level, **chosen):.4f}", flush=True)
    (ROOT / "runs" / "r4_fitted.json").write_text(json.dumps(chosen, indent=1))
