"""04-merge-plan.md §7 — the corrected side-by-side, on one harness and one vocabulary.

R1's and R2's published stress/ablation numbers came from different rewriters and different readings of
`no_spec_phrase`. These do not. This is the merge's deliverable.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import harness, race

CONDITIONS = (
    ("clean", {}),
    ("L1 scaffold", {"stress": 1}),
    ("L2 full", {"stress": 2}),
    ("L3 category", {"stress": 3}),
    ("no_spec_phrase", {"ablate": "no_spec_phrase"}),
    ("no_popularity", {"ablate": "no_popularity"}),
)

if __name__ == "__main__":
    out = {}
    print(f"{'road':<5s} {'condition':<16s} {'hit@10':>7s} {'MRR':>7s} {'MTTC':>6s} {'SCORE':>7s}",
          flush=True)
    for road in ("r1", "r2"):
        for label, kw in CONDITIONS:
            r = race.run_road(road, **kw)
            s = harness.score(r)
            lo, hi = harness.bootstrap_ci(r)
            out[f"{road}|{label}"] = {"hit": r["hit_rate_at_10"], "mrr": r["mrr"],
                                      "mttc": r["mttc"], "score": s, "ci": [lo, hi]}
            print(f"{road:<5s} {label:<16s} {r['hit_rate_at_10']:>7.3f} {r['mrr']:>7.4f} "
                  f"{r['mttc']:>6.2f} {s:>7.4f}  [{lo:.4f}, {hi:.4f}]", flush=True)
    (ROOT / "runs" / "merge_table.json").write_text(json.dumps(out, indent=1))
    print("\nwritten: runs/merge_table.json")
