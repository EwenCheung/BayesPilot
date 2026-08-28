"""The full R2 measurement: floors, ablations, fusion baseline, stress, and the R1 race.

    python3 -m src.eval.final

Writes one registry row per headline variant to runs/registry.jsonl and prints the comparison table.
R1 is run through the IDENTICAL harness and the IDENTICAL stress rewriter — a race where the two roads
are measured differently is not a race.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval import harness  # noqa: E402
from src.eval.compare import build, shared  # noqa: E402
from src.eval.stress import ParaphraseRewriter  # noqa: E402

RESULTS: dict[str, dict] = {}
HEADER = f"{'variant':<38s} {'hit@10':>6s} {'MRR':>7s} {'MTTC':>5s} {'SCORE':>7s}"


def show(label: str, result: dict) -> float:
    value = harness.score(result)
    print(f"{label:<38s} {result['hit_rate_at_10']:>6.3f} {result['mrr']:>7.4f} "
          f"{result['mttc']:>5.2f} {value:>7.4f}", flush=True)
    return value


def load_r1():
    path = ROOT / "experiments" / "agent_best_0.9607.py"
    spec = importlib.util.spec_from_file_location("r1_incumbent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Agent


def measure(label: str, make, stress: bool = True) -> dict:
    out = {"clean": harness.run(make())}
    show(label, out["clean"])
    if stress:
        for level in ("scaffold", "full"):
            out[level] = harness.run(make(), ParaphraseRewriter(level))
            show(f"  └ stressed:{level}", out[level])
    return out


def main() -> None:
    t0 = time.time()
    print(HEADER)
    print("=" * len(HEADER))

    print("\n--- reference points (identical harness) ---")
    r1_agent = load_r1()
    RESULTS["r1"] = measure("R1 incumbent (constraint filter)",
                            lambda: r1_agent(str(harness.CATALOG)))

    from src.eval import r1_hardened
    RESULTS["r1_hardened"] = measure(
        "R1 + popularity fallback (fair control)",
        lambda: r1_hardened.make(str(harness.CATALOG)))

    RESULTS["popularity"] = measure(
        "popularity + category only",
        lambda: build("none", ablations=("no_spec_phrase", "no_lexical", "no_dense")),
        stress=False)

    print("\n--- R2, offline dense backend (no network) ---")
    RESULTS["r2_svd"] = measure("R2 full (svd dense, offline)", lambda: build("svd"))

    have_bge = (ROOT / "artifacts" / "emb.npy").exists()
    if have_bge:
        print("\n--- R2, bge-m3 dense backend ---")
        # Clean only. bge-m3 needs one live API call per turn to embed the query, and the stressed
        # passes cannot reuse the cache; an earlier full run measured it statistically identical to the
        # offline backend under both stress levels, so the extra ~15 minutes buys nothing.
        RESULTS["r2_bge"] = measure("R2 full (bge-m3 dense)", lambda: build("bge"), stress=False)

    # Ablations run on the offline backend: bge-m3 measured statistically identical on both
    # clean and stressed, and needs a live API call per turn, which makes it 30x slower here.
    dense = "svd"
    print(f"\n--- ablations ({dense} dense) ---")
    for ablation in ("no_spec_phrase", "no_dense", "no_popularity", "no_lexical"):
        stress = ablation == "no_spec_phrase"  # the private-set insurance number, stressed too
        RESULTS[ablation] = measure(f"  {ablation}",
                                    lambda a=ablation: build(dense, ablations=(a,)), stress=stress)

    print("\n--- adaptive router (Pillar III) ---")
    RESULTS["no_adaptive"] = measure("  no_adaptive (fixed schedule)",
                                     lambda: build(dense, no_adaptive=True))

    print("\n--- fusion baseline ---")
    RESULTS["rrf"] = measure("RRF instead of scheduled blend",
                             lambda: build(dense, fuse="rrf"), stress=False)

    print("\n--- LLM semantic ranking stage (escalation only) ---")
    try:
        agent = build(dense, rerank=True)
        result = harness.run(agent)
        show("R2 + qwen3.6:35b listwise rerank", result)
        reranker = agent.reranker
        print(f"     llm calls={reranker.calls} failures={reranker.failures} "
              f"tokens={reranker.prompt_tokens + reranker.completion_tokens} "
              f"elapsed={result['elapsed_s']}s", flush=True)
        RESULTS["r2_rerank"] = {"clean": result, "_reranker": {
            "calls": reranker.calls, "failures": reranker.failures,
            "prompt_tokens": reranker.prompt_tokens,
            "completion_tokens": reranker.completion_tokens,
        }}
    except Exception as exc:  # noqa: BLE001
        print(f"  LLM rerank unavailable: {exc}", flush=True)

    # ---- registry -------------------------------------------------------------------------------
    headline = RESULTS["r2_svd"]   # the offline backend is what we recommend shipping
    ablations = {name: harness.score(RESULTS[name]["clean"])
                 for name in ("no_spec_phrase", "no_dense", "no_popularity", "no_lexical")
                 if name in RESULTS}
    ablations["rrf_instead_of_blend"] = harness.score(RESULTS["rrf"]["clean"])
    ablations["no_adaptive"] = harness.score(RESULTS["no_adaptive"]["clean"])
    ablations["no_spec_phrase_stressed_full"] = harness.score(RESULTS["no_spec_phrase"]["full"])
    rr = RESULTS.get("r2_rerank", {}).get("_reranker", {})

    harness.register(
        "r2-full", headline["clean"],
        paraphrase={"clean": harness.score(headline["clean"]),
                    "scaffold": harness.score(headline["scaffold"]),
                    "full": harness.score(headline["full"])},
        ablations=ablations,
        models={"embed": "tfidf-svd-256 (offline); bge-m3 measured equivalent",
                "rerank": "qwen3.6:35b" if rr else "none"},
        llm_call_failures=rr.get("failures", 0),
        notes="R2 = retrieve & rank. Headline metric is no_spec_phrase + stressed, not clean.",
    )
    harness.register(
        "r1-incumbent", RESULTS["r1"]["clean"],
        paraphrase={"clean": harness.score(RESULTS["r1"]["clean"]),
                    "scaffold": harness.score(RESULTS["r1"]["scaffold"]),
                    "full": harness.score(RESULTS["r1"]["full"])},
        notes="R1 run through the identical harness and stress rewriter, for the race.",
    )

    lo, hi = harness.bootstrap_ci(headline["clean"])
    print(f"\nR2 bootstrap 95% CI: [{lo}, {hi}]   (1000 resamples of the 200 sessions)")
    lo1, hi1 = harness.bootstrap_ci(RESULTS["r1"]["clean"])
    print(f"R1 bootstrap 95% CI: [{lo1}, {hi1}]")
    print(f"kit pristine: {harness.kit_is_pristine()}   total {time.time() - t0:.0f}s")

    (ROOT / "runs").mkdir(exist_ok=True)
    (ROOT / "runs" / "final_summary.json").write_text(json.dumps({
        name: {level: harness.summarize(res) for level, res in variant.items()
               if not level.startswith("_")}
        for name, variant in RESULTS.items()
    }, indent=2))


if __name__ == "__main__":
    main()
