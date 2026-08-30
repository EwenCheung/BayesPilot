"""The race — every road, one runner, one rewriter, one ablation vocabulary.

Before this existed, R1 and R2 each had their own harness, their own paraphrase rewriter and their own
reading of `no_spec_phrase`, so their robustness numbers were quoted side by side and meant nothing
(R1 defect 2, R2 defect A8). A road is just a name here; adding R3 adds a row to ROADS.

    python3 -m src.eval.race                              # every road, clean, on the public 200
    python3 -m src.eval.race --dataset dev --roads r4     # R4 on dev.jsonl, with CI + scenarios
    python3 -m src.eval.race --stress 2                   # ...at paraphrase level 2
    python3 -m src.eval.race --roads r1,r2                # a subset

⚠️ `--dataset` names one of `train | dev | public`, or a path. **`train` is the only set anything may
be fitted on**; `dev` and `public` are for reporting (src/eval/datasets.py).
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


def _r1(ablate: tuple[str, ...] = (), **kwargs):
    from src.r1.agent import Agent
    agent = Agent(str(harness.CATALOG), **kwargs)
    if ablate:
        agent.flags = ablations.r1_flags(*ablate)   # R1 reads flags from env at construction
    return agent


def _r2(ablate: tuple[str, ...] = (), **kwargs):
    from src.r2.agent import Agent
    return Agent(str(harness.CATALOG), ablations=ablations.r2_ablations(*ablate), **kwargs)


def _r5(ablate: tuple[str, ...] = (), **kwargs):
    from src.r5.agent import Agent
    agent = Agent(str(harness.CATALOG), **kwargs)
    if ablate:
        agent.flags = ablations.r4_flags(*ablate)
    return agent


def _r4(ablate: tuple[str, ...] = (), **kwargs):
    from src.r4.agent import Agent
    agent = Agent(str(harness.CATALOG), **kwargs)
    if ablate:
        agent.flags = ablations.r4_flags(*ablate)
    return agent


def _r3(ablate: tuple[str, ...] = (), **kwargs):
    from src.r3.agent import Agent
    agent = Agent(str(harness.CATALOG), **kwargs)
    if ablate:
        agent.flags = ablations.r3_flags(*ablate)
    return agent


# name -> factory. A road is a name; nothing else about the runner knows which is which.
ROADS = {"r1": _r1, "r2": _r2, "r3": _r3, "r4": _r4, "r5": _r5}


def run_road(road: str, stress: int = 0, ablate: str | tuple[str, ...] = (), **kwargs) -> dict:
    """Score one road at one paraphrase level, under one shared ablation vocabulary."""
    assert road in ROADS, f"unknown road {road!r}; have {sorted(ROADS)}"
    if isinstance(ablate, str):
        ablate = (ablate,)
    rewriter = ParaphraseRewriter(stress) if stress else None
    result = harness.run(ROADS[road](ablate=ablate, **kwargs), rewriter)
    assert harness.kit_is_pristine(), "kit drifted — this score is unverifiable"
    return result


def score_road(road: str, stress: int = 0, ablate: str | tuple[str, ...] = (), **kwargs) -> float:
    return harness.score(run_road(road, stress, ablate, **kwargs))


def main() -> None:
    parser = argparse.ArgumentParser(description="Score one or more roads on one dataset.")
    parser.add_argument("--roads", default=",".join(ROADS))
    parser.add_argument("--stress", type=int, default=0, help="paraphrase level 0-3")
    parser.add_argument("--dataset", default="public",
                        help="train | dev | public, or a path to a .jsonl")
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

    print(f"dataset {path.name}  n={len(samples)}  stress L{args.stress}\n")
    print(f"{'road':<8s} {'hit@10':>7s} {'MRR':>7s} {'MTTC':>6s} {'SCORE':>7s}"
          f"{'   95% CI' if args.ci else ''}")
    for road in args.roads.split(","):
        r = run_road(road.strip(), args.stress)
        ci = f"   ({harness.bootstrap_ci(r)[0]:.4f}, {harness.bootstrap_ci(r)[1]:.4f})" if args.ci else ""
        print(f"{road:<8s} {r['hit_rate_at_10']:>7.3f} {r['mrr']:>7.4f} "
              f"{r['mttc']:>6.2f} {harness.score(r):>7.4f}{ci}")
        if args.scenarios:
            for name in sorted(r["scenario_metrics"]):
                m = r["scenario_metrics"][name]
                print(f"    {name:<16s} n={m['sample_count']:<5} hit {m['hit_rate_at_10']:.4f} "
                      f"mrr {m['mrr']:.4f} mttc {m['mttc']:.2f}")
        print(f"    inference {r['elapsed_s']:.1f}s for {len(samples)} sessions "
              f"({1000 * r['elapsed_s'] / len(samples):.1f} ms/session)")


if __name__ == "__main__":
    main()
