"""The race, final. Three roads, one harness, one rewriter, one ablation vocabulary.

Everything R3 reports comes from here: the full-200 table for comparability with R1 and R2's published
numbers, the held-out 60 for generalisation, the ablations, and bootstrap CIs on all of it.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import harness, holdout, race          # harness puts the kit on sys.path
from evaluator.local_evaluator import evaluate       # noqa: E402
from src.eval.stress import ParaphraseRewriter       # noqa: E402

# Every number in the headline table is the OFFLINE path. Enforced, not assumed: a warm .cache/llm
# otherwise lifts L3 from 0.8297 to 0.8926 with zero network calls, which is invisible in the output.
os.environ["R3_OFFLINE"] = "1"

CONDITIONS = (("clean", 0, ()), ("L1 scaffold", 1, ()), ("L2 full", 2, ()), ("L3 category", 3, ()),
              ("no_spec_phrase", 0, ("no_spec_phrase",)), ("no_popularity", 0, ("no_popularity",)))
R3_ABLATIONS = (("belief_pool off L3", 3, ("no_belief_pool",)),
                ("belief_pool off L2", 2, ("no_belief_pool",)),
                ("EIG on, clean", 0, ("infogain",)),
                ("EIG on, L3", 3, ("infogain",)),
                ("no_lexical L3", 3, ("no_lexical",)),
                ("no_popularity L3", 3, ("no_popularity",)))


def line(label, road, r):
    s = harness.score(r)
    lo, hi = harness.bootstrap_ci(r)
    print(f"{road:<4s} {label:<16s} {r['hit_rate_at_10']:>6.3f} {r['mrr']:>7.4f} "
          f"{r['mttc']:>6.2f} {s:>7.4f}  [{lo:.4f}, {hi:.4f}]", flush=True)
    return {"hit": r["hit_rate_at_10"], "mrr": r["mrr"], "mttc": r["mttc"],
            "score": s, "ci": [lo, hi], "scenarios": r["scenario_metrics"]}


def subset_run(road, ids, stress=0):
    samples, cid, cats, prods = harness.load_world()
    keep = [s for s in samples if s["sample_id"] in ids]
    agent = race.ROADS[road]()
    subject = harness.StressedAgent(agent, ParaphraseRewriter(stress)) if stress else agent
    return evaluate(subject, keep, cid, cats, prods)


if __name__ == "__main__":
    out = {}
    print(f"{'road':<4s} {'condition':<16s} {'hit':>6s} {'MRR':>7s} {'MTTC':>6s} {'SCORE':>7s}  CI")
    print("== the race, all 200 sessions ==")
    for road in ("r1", "r2", "r3"):
        for label, stress, ablate in CONDITIONS:
            out[f"{road}|{label}"] = line(label, road, race.run_road(road, stress=stress, ablate=ablate))
        print()

    print("== R3 ablations ==")
    for label, stress, ablate in R3_ABLATIONS:
        out[f"r3|{label}"] = line(label, "r3", race.run_road("r3", stress=stress, ablate=ablate))

    print("\n== generalisation: tuned on the 140, read once on the 60 ==")
    split = holdout.load()
    for road in ("r1", "r2", "r3"):
        for half, ids in (("train140", split["train"]), ("test60", split["test"])):
            for lvl in (0, 3):
                r = subset_run(road, set(ids), lvl)
                out[f"{road}|{half}|L{lvl}"] = line(f"{half} L{lvl}", road, r)

    (ROOT / "runs" / "final.json").write_text(json.dumps(out, indent=1))
    print("\nwritten: runs/final.json")
