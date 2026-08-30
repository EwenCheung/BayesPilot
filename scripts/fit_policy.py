"""Fit R3's constants on the 140-session train split. The held-out 60 is not read here.

Staged rather than a full grid: the prior's units dominate everything downstream, so it is fitted
first and the policy is fitted underneath it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
os.environ["R3_OFFLINE"] = "1"                       # fit on the offline path (D22)

from src.eval import harness, holdout, race           # harness puts the kit on sys.path
from evaluator.local_evaluator import evaluate        # noqa: E402  (must follow harness)
from src.eval.stress import ParaphraseRewriter        # noqa: E402

_WORLD = None


def score_on(subset, stress=0, **overrides):
    global _WORLD
    if _WORLD is None:
        _WORLD = harness.load_world()
    samples, cid, cats, prods = _WORLD
    keep = [s for s in samples if s["sample_id"] in subset]
    agent = race.ROADS["r3"]()
    for k, v in overrides.items():
        setattr(agent.flags, k, v)
    subject = harness.StressedAgent(agent, ParaphraseRewriter(stress)) if stress else agent
    return harness.score(evaluate(subject, keep, cid, cats, prods))


def objective(subset, **kw):
    """Clean, L2 and L3 weighted equally. The private set is the target, not the public one, and two
    stress levels beat one — L2 and L3 fail differently (ranking vs recall, D13)."""
    return (score_on(subset, 0, **kw) + score_on(subset, 2, **kw) + score_on(subset, 3, **kw)) / 3


if __name__ == "__main__":
    train = set(holdout.load()["train"])
    chosen = {}

    print("stage 1 — prior weight (its units dominate everything else)")
    best = None
    for w in (0.10, 0.18, 0.26, 0.40):
        obj = objective(train, prior_weight=w)
        print(f"  prior_weight {w:>5.2f} | obj {obj:.4f}", flush=True)
        if best is None or obj > best[0]:
            best = (obj, w)
    chosen["prior_weight"] = best[1]
    print(f"  -> prior_weight = {best[1]}\n")

    print("stage 2 — patience (two stall decays: understood vs not understood)")
    best = None
    for v0 in (0.75, 0.90):
        for decay in (0.2, 0.35, 0.6):
            for clean_decay in (0.35, 0.6, 0.8):
                kw = dict(chosen, v_continue=v0, stall_decay=decay, stall_decay_clean=clean_decay)
                obj = objective(train, **kw)
                print(f"  v0 {v0:.2f} decay {decay:.2f} clean_decay {clean_decay:.2f} | "
                      f"obj {obj:.4f}", flush=True)
                if best is None or obj > best[0]:
                    best = (obj, v0, decay, clean_decay)
    chosen.update(v_continue=best[1], stall_decay=best[2], stall_decay_clean=best[3])
    print(f"  -> {chosen}\n")

    print("stage 3 — evidence gains")
    best = None
    for tau in (0.85, 0.90, 0.96):
        kw = dict(chosen, tau_mass=tau)
        obj = objective(train, **kw)
        print(f"  tau_mass {tau:.2f} | obj {obj:.4f}", flush=True)
        if best is None or obj > best[0]:
            best = (obj, tau)
    chosen["tau_mass"] = best[1]

    print(f"\nFITTED ON THE 140: {chosen}")
    print(f"  train clean {score_on(train, 0, **chosen):.4f}   train L3 {score_on(train, 3, **chosen):.4f}")
    import json
    (ROOT / "runs" / "r3_fitted.json").write_text(json.dumps(chosen, indent=1))
