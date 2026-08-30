"""Score the agent on one dataset, at one paraphrase level, under one ablation.

    python3 -m src.eval.measure --dataset dev --ci --scenarios
    python3 -m src.eval.measure --dataset public --stress 3 --ablate no_spec_phrase

This was `race.py` when five roads were competing for the same slot. Four lost; the runner stays
because every number in SUMMARY.md comes through it and through the kit's own `evaluate()`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval import ablations, harness  # noqa: E402
from src.eval.stress import ParaphraseRewriter  # noqa: E402


def build(ablate: tuple[str, ...] = ()):
    from src.copilot.agent import Agent
    agent = Agent(str(harness.CATALOG))
    if ablate:
        agent.flags = ablations.flags(*ablate)
    return agent


def run(stress: int = 0, ablate: str | tuple[str, ...] = ()) -> dict:
    if isinstance(ablate, str):
        ablate = (ablate,)
    rewriter = ParaphraseRewriter(stress) if stress else None
    result = harness.run(build(ablate), rewriter)
    assert harness.kit_is_pristine(), "kit drifted — this score is unverifiable"
    return result


def score(stress: int = 0, ablate: str | tuple[str, ...] = ()) -> float:
    return harness.score(run(stress, ablate))


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the agent on one dataset.")
    parser.add_argument("--stress", type=int, default=0, help="paraphrase level 0-3")
    parser.add_argument("--dataset", default="public",
                        help="train | dev | public, or a path to a .jsonl")
    parser.add_argument("--ablate", default="", help="comma-separated ablation names")
    parser.add_argument("--limit", type=int, default=0, help="first N sessions only (0 = all)")
    parser.add_argument("--ci", action="store_true", help="bootstrap 95%% CI, 1000 resamples")
    parser.add_argument("--scenarios", action="store_true", help="per-scenario breakdown")
    args = parser.parse_args()

    from src.eval import datasets
    named = {"train": datasets.TRAIN, "dev": datasets.DEV, "public": datasets.PUBLIC}
    path = named.get(args.dataset, Path(args.dataset))
    assert path.exists(), f"no such dataset: {path}"
    harness.DATASET = path
    harness._CACHE.pop("world", None)
    samples = harness.load_world()[0]
    if args.limit:
        samples = samples[:args.limit]
        harness._CACHE["world"] = (samples,) + harness.load_world()[1:]

    ablate = tuple(a.strip() for a in args.ablate.split(",") if a.strip())
    print(f"dataset {path.name}  n={len(samples)}  stress L{args.stress}"
          f"{'  ablate ' + ','.join(ablate) if ablate else ''}\n")
    r = run(args.stress, ablate)
    ci = ""
    if args.ci:
        lo, hi = harness.bootstrap_ci(r)
        ci = f"   95% CI ({lo:.4f}, {hi:.4f})"
    print(f"hit@10 {r['hit_rate_at_10']:.4f}   MRR {r['mrr']:.4f}   "
          f"MTTC {r['mttc']:.2f}   SCORE {harness.score(r):.4f}{ci}")
    if args.scenarios:
        for name in sorted(r["scenario_metrics"]):
            m = r["scenario_metrics"][name]
            print(f"    {name:<16s} n={m['sample_count']:<5} hit {m['hit_rate_at_10']:.4f} "
                  f"mrr {m['mrr']:.4f} mttc {m['mttc']:.2f}")
    print(f"    inference {r['elapsed_s']:.1f}s for {len(samples)} sessions "
          f"({1000 * r['elapsed_s'] / len(samples):.1f} ms/session)")


if __name__ == "__main__":
    main()
