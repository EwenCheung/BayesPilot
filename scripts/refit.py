"""Re-fit every tuned constant from scratch, on a dataset you choose.

    python3 scripts/refit.py --dataset data/train.jsonl --n 3000 --output runs/refit.json

There are **8 tuned constants** in this system and no trained weights, so this script *is* the
training pipeline. It searches the TechnicalScore itself — every objective evaluation is a full run of
the organizer's evaluator — rather than minimising a surrogate loss and hoping it transfers.

**Staged, not a grid.** The evidence gains dominate everything downstream, so they are fitted first
and the policy underneath them. Stage 2 is coordinate descent rather than a product: a full grid is
3^6 = 729 objectives at ~90 s each, and the parameters measured as near-separable.

⚠️ **`--dataset` must be a fitting set.** `dev.jsonl`, `public_set.jsonl` and every `*/test` split are
read for reporting only; pointing this at one of them silently invalidates every held-out number in
SUMMARY.md. The script refuses.

⚠️ **This writes JSON, not code.** The fitted values are literals in `src/copilot/flags.py`; adopting
a result is a deliberate edit, so a bad sweep cannot silently become the submission.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("COPILOT_OFFLINE", "1")   # fit on the offline path — a warm cache is not a run

from src.eval import harness                    # noqa: E402  harness puts the kit on sys.path
from evaluator.local_evaluator import evaluate  # noqa: E402  must follow harness
from src.eval.stress import ParaphraseRewriter  # noqa: E402
from src.copilot.agent import Agent             # noqa: E402

# name -> values to try, in the order they are fitted. Ranges are deliberately wide enough that a
# winner at the edge is visible: a boundary optimum is not an optimum, and extending one of these
# ranges once reversed its own conclusion.
STAGES: tuple[tuple[str, tuple[tuple[str, tuple]]], ...] = (
    ("evidence gains — their units dominate everything downstream", (
        ("exact_gain",        (2.0, 3.2, 4.5)),
        ("soft_card_gain",    (0.0, 1.0, 1.5, 2.5)),
        ("soft_card_floor",   (0.25, 0.34, 0.45)),
    )),
    ("the pool", (
        ("tau_mass",          (0.80, 0.85, 0.90, 0.96)),
        ("temperature",       (1.0, 2.0, 4.0)),
    )),
    ("patience, by coordinate descent", (
        ("v_continue",        (0.60, 0.75, 0.90, 0.97)),
        ("stall_decay",       (0.05, 0.2, 0.35, 0.6)),
        ("stall_decay_clean", (0.4, 0.6, 0.8, 0.95)),
    )),
)

_WORLD = None
_AGENT = None


def _agent(catalog: Path):
    """One agent, one index build. Rebuilding per objective would cost ~20 s x 100 evaluations."""
    global _AGENT
    if _AGENT is None:
        _AGENT = Agent(str(catalog))
    _AGENT.sessions.clear(); _AGENT._shipped.clear()
    _AGENT._stalls.clear(); _AGENT._last_asked.clear()
    return _AGENT


def score_on(samples, catalog: Path, level: int, **overrides) -> float:
    global _WORLD
    if _WORLD is None:
        _WORLD = harness.load_world()
    _, cid, cats, prods = _WORLD
    agent = _agent(catalog)
    base = {k: getattr(agent.flags, k) for k in overrides}
    for key, value in overrides.items():
        setattr(agent.flags, key, value)
    try:
        subject = harness.StressedAgent(agent, ParaphraseRewriter(level)) if level else agent
        return harness.score(evaluate(subject, samples, cid, cats, prods))
    finally:
        for key, value in base.items():           # never leak a sweep value into the next objective
            setattr(agent.flags, key, value)


def objective(samples, catalog: Path, levels: tuple[int, ...], **kw) -> float:
    """Every stress level weighted equally, so a change cannot buy clean score with robustness."""
    return sum(score_on(samples, catalog, lvl, **kw) for lvl in levels) / len(levels)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default="data/train.jsonl", help="fitting set (default: data/train.jsonl)")
    ap.add_argument("--catalog", default="data/catalog.jsonl")
    ap.add_argument("--n", type=int, default=3000, help="first N sessions (0 = all). Stress is ~40x clean")
    ap.add_argument("--levels", default="0,2,3", help="paraphrase levels in the objective, 0-4")
    ap.add_argument("--output", default="runs/refit.json")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    assert dataset.exists(), f"no such dataset: {dataset}"
    forbidden = ("dev.jsonl", "public_set.jsonl", "validation.jsonl", "test.jsonl")
    assert not any(dataset.name == f for f in forbidden), (
        f"{dataset.name} is a REPORTING set. Fitting on it invalidates every held-out number in "
        f"SUMMARY.md. Use data/train.jsonl, or a split you created for fitting.")

    catalog = Path(args.catalog)
    assert catalog.exists(), f"no such catalog: {catalog}"
    levels = tuple(int(x) for x in args.levels.split(","))

    harness.DATASET = dataset
    harness._CACHE.pop("world", None)
    samples = harness.load_world()[0]
    if args.n:
        samples = samples[:args.n]

    from src.copilot.flags import Flags
    tuned = [name for _, block in STAGES for name, _ in block]
    inherited = {k: getattr(Flags(), k) for k in tuned}

    print(f"refitting on {dataset.name}[:{len(samples)}] · levels {levels} · offline")
    print(f"⚠️ no reporting set is opened by this script\n")
    print(f"current values: {inherited}")
    t0 = time.time()
    base_obj = objective(samples, catalog, levels)
    print(f"baseline objective {base_obj:.4f}   [{time.time()-t0:.0f}s]\n", flush=True)

    chosen: dict = {}
    for title, block in STAGES:
        print(f"── {title}")
        for name, values in block:
            best = None
            for value in values:
                t1 = time.time()
                obj = objective(samples, catalog, levels, **dict(chosen, **{name: value}))
                edge = " ⚠️ EDGE" if value in (values[0], values[-1]) else ""
                print(f"   {name:<18} {value:>6} | obj {obj:.4f}{edge}  [{time.time()-t1:.0f}s]", flush=True)
                if best is None or obj > best[0]:
                    best = (obj, value)
            chosen[name] = best[1]
            at_edge = best[1] in (values[0], values[-1])
            print(f"   → {name} = {best[1]}  (obj {best[0]:.4f})"
                  f"{'   ⚠️ BOUNDARY OPTIMUM — extend the range and re-run' if at_edge else ''}\n", flush=True)

    fitted_obj = objective(samples, catalog, levels, **chosen)
    print(f"FITTED: {chosen}")
    print(f"  objective {base_obj:.4f} → {fitted_obj:.4f}  ({fitted_obj - base_obj:+.4f})")
    per_level = {}
    for lvl in levels:
        before = score_on(samples, catalog, lvl)
        after = score_on(samples, catalog, lvl, **chosen)
        per_level[f"L{lvl}"] = {"before": round(before, 4), "after": round(after, 4)}
        print(f"  L{lvl}: {before:.4f} → {after:.4f}  ({after - before:+.4f})", flush=True)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "dataset": str(dataset), "n": len(samples), "levels": list(levels),
        "inherited": inherited, "fitted": chosen,
        "objective": {"before": round(base_obj, 4), "after": round(fitted_obj, 4)},
        "per_level": per_level,
    }, indent=2))
    print(f"\n-> {out}")
    print("⚠️ Nothing was changed. To adopt a value, edit src/copilot/flags.py — the defaults ARE the "
          "submission, so adopting is a deliberate act.")


if __name__ == "__main__":
    main()
