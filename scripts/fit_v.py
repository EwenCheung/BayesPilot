"""Fit `v_continue` — the only free parameter in R3's policy — on the 140-session train split.

It is the expected reciprocal rank the agent believes it can still get by waiting. Low = impatient
(ship deep, lock in bad ranks); high = patient (hold for rank 1, pay turns).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import harness, holdout, race
from src.r3.flags import Flags


def score_on(subset: set[str], v: float, stress: int = 0) -> dict:
    """Score R3 over only the named sessions, by filtering the world the harness sees."""
    samples, catalog_ids, categories, products = harness.load_world()
    keep = [s for s in samples if s["sample_id"] in subset]
    from evaluator.local_evaluator import evaluate
    from src.eval.stress import ParaphraseRewriter
    agent = race.ROADS["r3"]()
    agent.flags = Flags.from_env()
    agent.flags.v_continue = v
    subject = harness.StressedAgent(agent, ParaphraseRewriter(stress)) if stress else agent
    return evaluate(subject, keep, catalog_ids, categories, products)


if __name__ == "__main__":
    split = holdout.load()
    train, test = set(split["train"]), set(split["test"])
    print(f"{'v':>6s} | {'train clean':>11s} {'MRR':>7s} {'MTTC':>6s} | {'train L3':>9s}")
    best = None
    for v in (0.75, 0.82, 0.88, 0.92, 0.95, 0.98):
        clean = score_on(train, v)
        s = harness.score(clean)
        l3 = harness.score(score_on(train, v, stress=3))
        print(f"{v:>6.2f} | {s:>11.4f} {clean['mrr']:>7.4f} {clean['mttc']:>6.2f} | {l3:>9.4f}",
              flush=True)
        # the private set is the target, so weight the stressed condition equally with clean
        objective = 0.5 * s + 0.5 * l3
        if best is None or objective > best[0]:
            best = (objective, v, s, l3)
    print(f"\nchosen on the 140: v_continue={best[1]} (clean {best[2]:.4f}, L3 {best[3]:.4f})")
