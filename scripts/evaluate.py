"""The four-dataset table in `docs/R5-RESULTS.md` §1, one run.

    R3_OFFLINE=1 PYTHONHASHSEED=0 python3 scripts/final_r5.py            # offline everywhere
    PYTHONHASHSEED=0 python3 scripts/final_r5.py                         # freeform gets the LLM tier

⚠️ Only `freeform_v1/test` uses the LLM, and only as the escalation tier `parse()` already gates —
every other dataset is templated, reads deterministically, and never reaches it.
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
from src.eval import freeform, harness  # noqa: E402
from src.copilot.agent import Agent  # noqa: E402

_, CID, CATS, PRODS = harness.load_world()




def run(samples, wrap: bool, bm25: float = 0.0):
    agent = Agent(str(harness.CATALOG))          # defaults only — this IS the submission (D2)
    agent.flags.bm25_gain = bm25
    subject = freeform.FreeFormAgent(agent, samples) if wrap else agent
    t0 = time.time()
    result = evaluate(subject, samples, CID, CATS, PRODS)
    calls = getattr(agent.llm, "calls", 0) if agent.llm is not None else 0
    return result, harness.score(result), time.time() - t0, calls


def main() -> None:
    rows = []
    for label, samples, wrap in (
        ("freeform_v1/test", freeform.split("freeform", "test"), True),
        ("resplit_60_20_20/test", freeform.split("resplit", "test"), False),
        ("public_set.jsonl", harness.load_jsonl(ROOT / "data" / "public_set.jsonl"), False),
        ("dev.jsonl", harness.load_jsonl(ROOT / "data" / "dev.jsonl"), False),
    ):
        for bm25 in (0.0,):
            r, score, wall, calls = run(samples, wrap, bm25)
            lo, hi = harness.bootstrap_ci(r)
            rows.append({"dataset": label, "n": len(samples), "bm25_gain": bm25,
                         "hit_rate_at_10": round(r["hit_rate_at_10"], 4),
                         "mrr": round(r["mrr"], 4), "mttc": round(r["mttc"], 2),
                         "technical_score": round(score, 4), "ci": [round(lo, 4), round(hi, 4)],
                         "llm_calls": calls, "seconds": round(wall, 1)})
            print(f"{label:<24} bm25={bm25:<4} n={len(samples):<5} "
                  f"hit {r['hit_rate_at_10']:.4f}  mrr {r['mrr']:.4f}  mttc {r['mttc']:.2f}  "
                  f"score {score:.4f}  CI ({lo:.4f}, {hi:.4f})  calls={calls}  {wall:.0f}s",
                  flush=True)
    (ROOT / "runs" / "final_r5.json").write_text(json.dumps(rows, indent=2))
    print("\n-> runs/final_r5.json")


if __name__ == "__main__":
    main()
