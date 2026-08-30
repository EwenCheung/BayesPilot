"""The race — every road, one runner, one rewriter, one ablation vocabulary.

Before this existed, R1 and R2 each had their own harness, their own paraphrase rewriter and their own
reading of `no_spec_phrase`, so their robustness numbers were quoted side by side and meant nothing
(R1 defect 2, R2 defect A8). A road is just a name here; adding R3 adds a row to ROADS.

    python3 -m src.eval.race                 # every road, clean
    python3 -m src.eval.race --stress 2      # every road at paraphrase level 2
    python3 -m src.eval.race --roads r1,r2   # a subset
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


def _r3(ablate: tuple[str, ...] = (), **kwargs):
    from src.r3.agent import Agent
    agent = Agent(str(harness.CATALOG), **kwargs)
    if ablate:
        agent.flags = ablations.r3_flags(*ablate)
    return agent


# name -> factory. A road is a name; nothing else about the runner knows which is which.
ROADS = {"r1": _r1, "r2": _r2, "r3": _r3}


def run_road(
    road: str,
    stress: int = 0,
    ablate: str | tuple[str, ...] = (),
    *,
    sample_limit: int | None = None,
    **kwargs,
) -> dict:
    """Score one road at one paraphrase level, under one shared ablation vocabulary."""
    assert road in ROADS, f"unknown road {road!r}; have {sorted(ROADS)}"
    if isinstance(ablate, str):
        ablate = (ablate,)
    rewriter = ParaphraseRewriter(stress) if stress else None
    result = harness.run(
        ROADS[road](ablate=ablate, **kwargs),
        rewriter,
        dataset=harness.TRAIN_DATASET,
        sample_limit=sample_limit,
    )
    assert harness.kit_is_pristine(), "kit drifted — this score is unverifiable"
    return result


def score_road(
    road: str,
    stress: int = 0,
    ablate: str | tuple[str, ...] = (),
    *,
    sample_limit: int | None = None,
    **kwargs,
) -> float:
    return harness.score(
        run_road(road, stress, ablate, sample_limit=sample_limit, **kwargs)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roads", default=",".join(ROADS))
    parser.add_argument("--stress", type=int, default=0)
    args = parser.parse_args()

    print(f"{'road':<8s} {'hit@10':>7s} {'MRR':>7s} {'MTTC':>6s} {'SCORE':>7s}")
    for road in args.roads.split(","):
        r = run_road(road.strip(), args.stress)
        print(f"{road:<8s} {r['hit_rate_at_10']:>7.3f} {r['mrr']:>7.4f} "
              f"{r['mttc']:>6.2f} {harness.score(r):>7.4f}")


if __name__ == "__main__":
    main()
