"""Policy sweep: depth ladder x deadline, then slot decay and spec partial credit.

All remaining headroom is MRR (+0.075 vs +0.012 from speed), and MRR is bought by patience: a hit ENDS
the session and locks in that rank. So the knobs that matter are how eagerly the ladder ships depth and
how long the deadline waits.

Runs on the resplit train data; test and public are reserved for locked final evaluation.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval import harness  # noqa: E402
from src.eval.r2_variants import build  # noqa: E402

LADDERS = {
    "eager":    ((0.40, 10), (0.20, 4), (0.10, 2), (0.00, 1)),
    "baseline": ((0.55, 10), (0.30, 4), (0.15, 2), (0.00, 1)),
    "patient":  ((0.70, 10), (0.45, 3), (0.25, 2), (0.00, 1)),
    "strict":   ((0.80, 10), (0.60, 2), (0.00, 1)),
    "top1":     ((0.75, 10), (0.00, 1)),
}


def main(dense: str = "svd", ladders: tuple[str, ...] = (), deadlines: tuple[int, ...] = (2, 3, 4)) -> None:
    print(f"dense={dense}")
    print(f"{'ladder':<10s} {'dl':>3s}  {'hit@10':>6s}  {'MRR':>6s}  {'MTTC':>5s}  {'SCORE':>6s}")
    print("-" * 48)
    best = (None, -1.0)
    chosen = {k: v for k, v in LADDERS.items() if not ladders or k in ladders}
    for name, ladder in chosen.items():
        for deadline in deadlines:
            agent = build(dense, ladder=ladder, deadline=deadline)
            result = harness.run(agent, dataset=harness.TRAIN_DATASET)
            score = harness.score(result)
            flag = ""
            if score > best[1]:
                best = ((name, deadline), score)
                flag = "  <-"
            print(f"{name:<10s} {deadline:>3d}  {result['hit_rate_at_10']:.3f}  {result['mrr']:.4f}  "
                  f"{result['mttc']:.2f}  {score:.4f}{flag}", flush=True)
    print(f"\nbest: ladder={best[0][0]} deadline={best[0][1]} score={best[1]:.4f}")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[0] if args else "svd",
         tuple(args[1].split(",")) if len(args) > 1 else (),
         tuple(int(x) for x in args[2].split(",")) if len(args) > 2 else (2, 3, 4))
