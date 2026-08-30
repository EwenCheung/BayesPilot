"""The model x test-set matrix in `docs/SUMMARY.md`.

Rows are roads, columns are the three held-out test files. Every cell is one run of the OFFICIAL
`evaluator.local_evaluator.evaluate()`; only the sample list changes.

    R3_OFFLINE=1 PYTHONHASHSEED=0 R4_FLAGS=exclude_shipped python3 scripts/matrix.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "techjam-conversational-search-main"))

from evaluator.local_evaluator import evaluate  # noqa: E402
from src.eval import freeform, harness, race  # noqa: E402

_, CID, CATS, PRODS = harness.load_world()

COLUMNS = (
    ("freeform_v1/test", lambda: freeform.split("freeform", "test"), True),
    ("resplit_60_20_20/test", lambda: freeform.split("resplit", "test"), False),
    ("public_set.jsonl", lambda: harness.load_jsonl(ROOT / "data" / "public_set.jsonl"), False),
)




def main() -> None:
    roads = sys.argv[1].split(",") if len(sys.argv) > 1 else ["r1", "r2", "r3", "r4", "r5"]
    rows = []
    for road in roads:
        for label, load, wrap in COLUMNS:
            samples = load()
            agent = race.ROADS[road]()
            subject = freeform.FreeFormAgent(agent, samples) if wrap else agent
            t0 = time.time()
            r = evaluate(subject, samples, CID, CATS, PRODS)
            lo, hi = harness.bootstrap_ci(r)
            row = {"road": road, "dataset": label, "n": len(samples),
                   "hit_rate_at_10": round(r["hit_rate_at_10"], 4),
                   "mrr": round(r["mrr"], 4), "mttc": round(r["mttc"], 2),
                   "technical_score": round(harness.score(r), 4), "ci": [lo, hi],
                   "llm_calls": getattr(agent, "llm", None) and getattr(agent.llm, "calls", 0) or 0,
                   "seconds": round(time.time() - t0, 1)}
            rows.append(row)
            print(f"{road:<4} {label:<24} n={row['n']:<5} hit {row['hit_rate_at_10']:.4f} "
                  f"mrr {row['mrr']:.4f} mttc {row['mttc']:.2f} score {row['technical_score']:.4f} "
                  f"CI ({lo:.4f},{hi:.4f})  {row['seconds']:.0f}s", flush=True)
    (ROOT / "runs" / "matrix.json").write_text(json.dumps(rows, indent=2))
    print("\n-> runs/matrix.json")


if __name__ == "__main__":
    main()
