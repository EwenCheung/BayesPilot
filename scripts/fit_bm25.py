"""Sweep `bm25_gain` on train.jsonl at L0/L2/L3 (D24).

⚠️ Fitted on `train.jsonl`. D19/D20/D23 — the routes BM25 is being compared against — predate
`train.jsonl` and were measured on the public 200, so this is the first lexical route measured under
the current discipline.

    R3_OFFLINE=1 PYTHONHASHSEED=0 python3 scripts/fit_bm25.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "techjam-conversational-search-main"))

from evaluator.local_evaluator import evaluate  # noqa: E402

from src.eval import harness, stress  # noqa: E402
from src.copilot.agent import Agent  # noqa: E402

LIMIT = 3000   # stress over all 12,000 is ~7 min per cell; 3,000 is the same set fit_r4 used

harness.DATASET = ROOT / "data" / "train.jsonl"
SAMPLES, CID, CATS, PRODS = harness.load_world()
SAMPLES = SAMPLES[:LIMIT]

BASE = Agent(str(harness.CATALOG))      # build the 50k index ONCE and reuse it
BASE.flags.exclude_shipped = True


def run(gain: float, level: int) -> float:
    BASE.sessions.clear(); BASE._shipped.clear()
    BASE._stalls.clear(); BASE._last_asked.clear()
    BASE.flags.bm25_gain = gain
    subject = BASE
    if level:
        subject = harness.StressedAgent(BASE, stress.ParaphraseRewriter(level))
    return harness.score(evaluate(subject, SAMPLES, CID, CATS, PRODS))


def main() -> None:
    grid = (0.0, 0.5, 1.0, 2.0, 4.0)
    base_mean = None
    for gain in grid:
        cells = {}
        for level in (0, 2, 3):
            t0 = time.time()
            cells[level] = run(gain, level)
            print(f"  bm25_gain={gain:<4} L{level}  {cells[level]:.4f}  [{time.time()-t0:.0f}s]",
                  flush=True)
        mean = sum(cells.values()) / 3
        if base_mean is None:
            base_mean = mean
        print(f"bm25_gain={gain:<4} mean {mean:.4f}  ({mean - base_mean:+.4f})\n", flush=True)
    print("DONE")


if __name__ == "__main__":
    main()
