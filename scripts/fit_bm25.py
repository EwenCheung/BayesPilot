"""Sweep `bm25_gain` on train.jsonl at L0/L2/L3, and price the tokenizer repair separately.

Two questions, one run:

1. **What gain?** The first sweep put the optimum at the top of its range (4.0), and a boundary
   optimum is not an optimum — extending the `prior_weight` range on exactly that reasoning is what
   changed its conclusion. So the grid runs past where the first one stopped.
2. **How much of this is BM25, and how much is the tokenizer?** `understand/tokens.py` repaired three
   defects in the surface BM25 reads. The legacy row re-runs the winning gain through the ORIGINAL
   `attributes.tokens()` — frozenset, `len > 2`, no `%` — so the two effects are separable instead of
   being credited to whichever one was changed last.

⚠️ Fitted on `train.jsonl`. D19/D20/D23 — the routes BM25 is being compared against — predate
`train.jsonl` and were measured on the public 200, so this is the first lexical route measured under
the current discipline.

    COPILOT_OFFLINE=1 PYTHONHASHSEED=0 python3 scripts/fit_bm25.py
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


def run(gain: float, level: int) -> float:
    BASE.sessions.clear(); BASE._shipped.clear()
    BASE._stalls.clear(); BASE._last_asked.clear()
    BASE.flags.bm25_gain = gain
    subject = BASE
    if level:
        subject = harness.StressedAgent(BASE, stress.ParaphraseRewriter(level))
    return harness.score(evaluate(subject, SAMPLES, CID, CATS, PRODS))


def main() -> None:
    grid = (0.0, 2.0, 3.0, 4.0, 6.0, 8.0)
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
    # --- how much of that was the tokenizer, not BM25? -----------------------------------------
    import src.retrieve.bm25 as bm25_module
    from src.understand.attributes import tokens as legacy_tokens

    print("legacy tokenizer (frozenset, len>2, no %) at each gain:", flush=True)
    original = bm25_module.terms
    bm25_module.terms = lambda text: sorted(legacy_tokens(text))   # a set, so tf collapses to 1
    for gain in (2.0, 4.0):
        BASE.index.__dict__.pop("_bm25", None)
        cells = {level: run(gain, level) for level in (0, 2, 3)}
        mean = sum(cells.values()) / 3
        print(f"  LEGACY bm25_gain={gain:<4} L0 {cells[0]:.4f}  L2 {cells[2]:.4f}  "
              f"L3 {cells[3]:.4f}  mean {mean:.4f}  ({mean - base_mean:+.4f})", flush=True)
    bm25_module.terms = original
    BASE.index.__dict__.pop("_bm25", None)
    print("DONE")


if __name__ == "__main__":
    main()
