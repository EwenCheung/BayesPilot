"""Fit R3's constants on the 8,400-session train split. Test/public are not read here.

Staged rather than a full grid: the prior's units dominate everything downstream, so it is fitted
first and the policy is fitted underneath it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
os.environ["R3_OFFLINE"] = "1"                       # fit on the offline path (D22)

from src.eval import harness, race                    # harness puts the kit on sys.path
from evaluator.local_evaluator import evaluate        # noqa: E402  (must follow harness)
from src.eval.stress import ParaphraseRewriter        # noqa: E402

_WORLD = None


def score_on(split="train", stress=0, **overrides):
    global _WORLD
    dataset = {
        "train": harness.TRAIN_DATASET,
        "validation": harness.VALIDATION_DATASET,
    }[split]
    if _WORLD is None or _WORLD[0] != split:
        _WORLD = (split, harness.load_world(dataset))
    _, world = _WORLD
    samples, cid, cats, prods = world
    agent = race.ROADS["r3"]()
    for k, v in overrides.items():
        setattr(agent.flags, k, v)
    subject = harness.StressedAgent(agent, ParaphraseRewriter(stress)) if stress else agent
    return harness.score(evaluate(subject, samples, cid, cats, prods))


def objective(split="train", **kw):
    """Clean, L2 and L3 weighted equally. The private set is the target, not the public one, and two
    stress levels beat one — L2 and L3 fail differently (ranking vs recall, D13)."""
    return (score_on(split, 0, **kw) + score_on(split, 2, **kw) + score_on(split, 3, **kw)) / 3


if __name__ == "__main__":
    train = "train"
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

    print(f"\nFITTED ON RESPLIT TRAIN (8,400): {chosen}")
    print(f"  train clean {score_on(train, 0, **chosen):.4f}   train L3 {score_on(train, 3, **chosen):.4f}")
    import json
    (ROOT / "runs" / "r3_fitted.json").write_text(json.dumps(chosen, indent=1))
