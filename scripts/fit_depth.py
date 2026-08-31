"""D25 — does showing more items early help? Two knobs, swept on train.jsonl.

  A. `v_continue`  lowers the value of waiting, so the expected-utility policy itself widens.
  B. `min_depth`   an explicit floor that OVERRIDES the policy.

⚠️ Fitted on `train.jsonl`. Reported on the four held-out sets by `scripts/final_r5.py`.

    R3_OFFLINE=1 PYTHONHASHSEED=0 python3 scripts/fit_depth.py
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
from src.r5.agent import Agent  # noqa: E402

LIMIT = 3000

harness.DATASET = ROOT / "train.jsonl"
SAMPLES, CID, CATS, PRODS = harness.load_world()
SAMPLES = SAMPLES[:LIMIT]

BASE = Agent(str(harness.CATALOG))
BASE.flags.exclude_shipped = True


def run(level: int, **over):
    BASE.sessions.clear(); BASE._shipped.clear()
    BASE._stalls.clear(); BASE._last_asked.clear()
    BASE.flags.v_continue = 0.75
    BASE.flags.min_depth = 0
    for k, v in over.items():
        setattr(BASE.flags, k, v)
    subject = BASE
    if level:
        subject = harness.StressedAgent(BASE, stress.ParaphraseRewriter(level))
    r = evaluate(subject, SAMPLES, CID, CATS, PRODS)
    return r, harness.score(r)


def line(label, **over):
    row = {}
    for level in (0, 3):
        t0 = time.time()
        r, sc = run(level, **over)
        row[level] = (sc, r["hit_rate_at_10"], r["mrr"], r["mttc"], time.time() - t0)
    (c, ch, cm, ct, cw), (s, sh, sm, st, sw) = row[0], row[3]
    print(f"{label:<22} L0 {c:.4f} (hit {ch:.4f} mrr {cm:.4f} mttc {ct:.2f}) | "
          f"L3 {s:.4f} (hit {sh:.4f} mrr {sm:.4f}) | mean {(c+s)/2:.4f}  [{cw+sw:.0f}s]", flush=True)
    return (c + s) / 2


def main():
    print("=== SHIPPED baseline ===")
    base = line("v_continue=0.75")

    print("\n=== A. lower v_continue — the policy widens on its own ===")
    for v in (0.50, 0.40, 0.35, 0.30, 0.25, 0.20):
        m = line(f"v_continue={v}", v_continue=v)
        print(f"{'':22}   vs shipped {m - base:+.4f}", flush=True)

    print("\n=== B. explicit floor, policy otherwise unchanged ===")
    for d in (2, 3, 4, 5):
        m = line(f"min_depth={d}", min_depth=d)
        print(f"{'':22}   vs shipped {m - base:+.4f}", flush=True)
    print("\nDONE")


if __name__ == "__main__":
    main()
