"""Was any DECISION (not just a parameter) made by looking at the held-out 60?

Parameter fitting used the 140 only. But several structural choices — switching EIG off, dropping the
semantic term — were made from full-200 ablations, which include the 60. This re-runs those decisions
on each half separately: if the sign flips on the held-out half, the decision was luck.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import harness, holdout, race           # noqa: E402
from evaluator.local_evaluator import evaluate        # noqa: E402
from src.eval.stress import ParaphraseRewriter        # noqa: E402

_W = None


def run(ids, stress=0, **flags):
    global _W
    if _W is None:
        _W = harness.load_world()
    samples, cid, cats, prods = _W
    keep = [s for s in samples if s["sample_id"] in ids]
    agent = race.ROADS["r3"]()
    for k, v in flags.items():
        setattr(agent.flags, k, v)
    if flags.get("semantic_gain"):
        from src.r3.semantic import BlairSemantics
        agent.semantics = BlairSemantics(agent.index, query_mode="model")
    subject = harness.StressedAgent(agent, ParaphraseRewriter(stress)) if stress else agent
    return harness.score(evaluate(subject, keep, cid, cats, prods))


if __name__ == "__main__":
    split = holdout.load()
    train, test = set(split["train"]), set(split["test"])
    allids = train | test

    print("DECISION 1 — switching EIG off (was decided on all 200)")
    print(f"{'':<12s} {'train140':>9s} {'test60':>9s} {'all200':>9s}")
    for lvl in (0, 3):
        on = [run(s, lvl, infogain=True) for s in (train, test, allids)]
        off = [run(s, lvl, infogain=False) for s in (train, test, allids)]
        print(f"  L{lvl} EIG on  {on[0]:>9.4f} {on[1]:>9.4f} {on[2]:>9.4f}")
        print(f"  L{lvl} EIG off {off[0]:>9.4f} {off[1]:>9.4f} {off[2]:>9.4f}")
        print(f"  L{lvl} delta   {off[0]-on[0]:>+9.4f} {off[1]-on[1]:>+9.4f} {off[2]-on[2]:>+9.4f}",
              flush=True)

    print("\nDECISION 2 — dropping the BLaIR semantic term (was decided on all 200)")
    for lvl in (0, 3):
        with_ = [run(s, lvl, semantic_gain=2.5, semantic_backend="blair") for s in (train, test)]
        without = [run(s, lvl, semantic_gain=0.0) for s in (train, test)]
        print(f"  L{lvl} delta (without − with) "
              f"{without[0]-with_[0]:>+8.4f} {without[1]-with_[1]:>+8.4f}", flush=True)
