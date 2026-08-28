"""Sweep the fusion schedule and the spec route's two constants.

The question this answers: once every stated constraint is matched exactly, MANY products can tie. Which
route should break that tie — popularity (the 570x target skew, a real prior on being the answer) or
dense similarity (which is close to uninformative between products that all satisfy the same specs)?
Guessing produced a change that made the score worse, so it is measured instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval import harness  # noqa: E402
from src.eval.compare import build  # noqa: E402


def schedule(pop3: float, spec3: float, lex3: float, dense3: float) -> dict:
    """Interpolate the 0..3-slot schedule from the fully-informed endpoint."""
    return {
        0: (1.00, 0.00, 0.20, 0.20),
        1: (pop3 + 0.23, spec3 * 0.50, lex3, dense3 * 0.75),
        2: (pop3 + 0.08, spec3 * 0.77, lex3, dense3 * 0.92),
        3: (pop3, spec3, lex3, dense3),
    }


GRID = [
    ("pop2.5 spec6    ", 2.50, 6.0, 0.30, 0.60),
    ("pop2.5 spec9    ", 2.50, 9.0, 0.30, 0.60),
    ("pop2.5 spec14   ", 2.50, 14.0, 0.30, 0.60),
    ("pop3.5 spec9    ", 3.50, 9.0, 0.30, 0.60),
    ("pop1.5 spec9    ", 1.50, 9.0, 0.30, 0.60),
    ("pop2.5 spec9 d.9", 2.50, 9.0, 0.30, 0.90),
    ("pop2.5 spec9 l.6", 2.50, 9.0, 0.60, 0.60),
]
BONUSES = (0.0,)   # the exactness step was swept and removed - it lost in 8/8 configurations


def main() -> None:
    print(f"{'schedule':<18s} {'bon':>4s}  {'hit@10':>6s}  {'MRR':>6s}  {'MTTC':>5s}  {'SCORE':>6s}")
    print("-" * 56)
    best = (None, -1.0)
    for label, pop3, spec3, lex3, dense3 in GRID:
        for bonus in BONUSES:
            agent = build("svd", schedule=schedule(pop3, spec3, lex3, dense3))
            result = harness.run(agent)
            value = harness.score(result)
            flag = ""
            if value > best[1]:
                best = ((label.strip(), bonus), value)
                flag = "  <-"
            print(f"{label:<18s} {bonus:>4.1f}  {result['hit_rate_at_10']:.3f}  {result['mrr']:.4f}  "
                  f"{result['mttc']:.2f}  {value:.4f}{flag}", flush=True)
    print(f"\nbest: {best[0]} score={best[1]:.4f}")


if __name__ == "__main__":
    main()
