"""Spec 3.10 — run the full measurement matrix and write the registry.

Every route is behind a flag, so "does this component earn its place?" is a run, not an argument.
`no_spec_phrase` is the standing honesty metric: it is our estimate of what survives if the private
set is paraphrased (IMPORTANT.md §3).
"""
from __future__ import annotations

import json
import sys

from src.eval import compare, run

# name -> (R1_FLAGS, R1_STRESS)
MATRIX: dict[str, tuple[str, str]] = {
    # --- headline: what we would ship ---
    "r1_ship":              ("", "0"),                       # shipping defaults: extract + adaptive rerank
    "r1_ship_stress2":      ("", "2"),
    "r1_ship_stress3":      ("", "3"),
    "r1_offline":           ("", "0"),                       # R1_OFFLINE=1 added below — A7
    "abl_no_adaptive":      ("no_adaptive", "0"),
    "disclosure_stress2":   ("", "2"),   # run with R1_LLM_NOCACHE=1 for real latency
    "abl_no_hedge_s3":      ("no_hedge", "3"),
    "abl_no_hedge_s2":      ("no_hedge", "2"),
    "abl_no_adaptive_s2":   ("no_adaptive", "2"),
    "r1_clean":             ("no_llm_extract,no_llm_rerank", "0"),   # deterministic only, no network
    "r1_full":              ("llm_extract,llm_rerank,no_adaptive", "0"),  # every route on, always
    "r1_extract":           ("llm_extract,no_llm_rerank", "0"),
    # --- the referee: does it survive being reworded? ---
    "r1_stress1":           ("no_llm_extract,no_llm_rerank", "1"),
    "r1_stress2":           ("no_llm_extract,no_llm_rerank", "2"),
    "r1_stress1_llm":       ("llm_extract,no_llm_rerank", "1"),
    "r1_stress2_llm":       ("llm_extract,no_llm_rerank", "2"),
    "r1_stress2_llm_dense": ("llm_extract,no_llm_rerank,dense", "2"),
    "r1_stress2_llm_rerank": ("llm_extract,llm_rerank,no_adaptive", "2"),
    "r1_stress3_llm":       ("llm_extract,no_llm_rerank", "3"),   # model-written paraphrase
    # --- ablations on clean text: does each route earn its place? ---
    "abl_no_spec_phrase":   ("no_llm_extract,no_llm_rerank,no_spec_phrase", "0"),         # the standing honesty metric
    "abl_no_attribute":     ("no_llm_extract,no_llm_rerank,no_attribute", "0"),
    "abl_no_token":         ("no_llm_extract,no_llm_rerank,no_token", "0"),
    "abl_no_popularity":    ("no_llm_extract,no_llm_rerank,no_popularity", "0"),
    "abl_no_infogain":      ("no_llm_extract,no_llm_rerank,no_infogain", "0"),
    "abl_truncate":         ("no_llm_extract,no_llm_rerank,truncate", "0"),
    "abl_profile":          ("no_llm_extract,no_llm_rerank,profile", "0"),
    "abl_dense":            ("no_llm_extract,no_llm_rerank,dense", "0"),
    "abl_erase_delete":     ("no_llm_extract,no_llm_rerank,erase=delete", "0"),
    "abl_erase_keep":       ("no_llm_extract,no_llm_rerank,erase=keep", "0"),
    "abl_deadline2":        ("no_llm_extract,no_llm_rerank,deadline=2", "0"),
    "abl_deadline4":        ("no_llm_extract,no_llm_rerank,deadline=4", "0"),
    "abl_shrink_fuzzy":     ("no_llm_extract,no_llm_rerank,shrink_min=0.6", "0"),
    # --- ablations under stress: what actually carries the weight when the words change ---
    "abl_no_spec_stress2":  ("no_llm_extract,no_llm_rerank,no_spec_phrase", "2"),
    "abl_no_attr_stress2":  ("no_llm_extract,no_llm_rerank,no_attribute", "2"),
    "abl_no_pop_stress2":   ("no_llm_extract,no_llm_rerank,no_popularity", "2"),
    "abl_no_token_stress2": ("no_llm_extract,no_llm_rerank,no_token", "2"),
}


def execute(names: list[str]) -> list[dict]:
    rows = []
    for name in names:
        flags, stress = MATRIX[name]
        environment = {"R1_FLAGS": flags, "R1_STRESS": stress}
        if name.startswith("disclosure"):
            environment["R1_LLM_NOCACHE"] = "1"
        if name == "r1_offline":
            environment["R1_OFFLINE"] = "1"   # A7: prove the no-network path scores the same
        result = run.run(name, environment)
        record = compare.row(result, {"flags": flags, "stress": int(stress)})
        compare.append(record)
        rows.append(record)
        print(f"{name:22s} score={record['technical_score']:.4f} "
              f"ci={record['ci95']} hit={record['hit_rate_at_10']:.3f} "
              f"mrr={record['mrr']:.4f} mttc={record['mttc']:.2f} ({record['wall_clock_s']}s)", flush=True)
    return rows


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(MATRIX)
    print(json.dumps([r["variant"] for r in execute(wanted)]))
