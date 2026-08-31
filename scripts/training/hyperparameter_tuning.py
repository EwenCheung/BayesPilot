"""Re-fit every tuned constant from scratch, on a dataset you choose.

    python3 scripts/training/hyperparameter_tuning.py --dataset data/train.jsonl --n 3000 --output runs/refit.json

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
a result is a deliberate edit, so a bad sweep cannot silently become the submission. The run ends by
printing both forms of the result — a `COPILOT_FLAGS=` line for `.env` to try it locally, and the
`flags.py` literals to actually ship it.

**One flag, one range** — `--sweep` replaces the staged fit with a single parameter's curve. This is
what `scripts/fit_bm25.py` was, and it was a second implementation of `objective()` that did not set
`COPILOT_OFFLINE` and averaged its levels by hand, so its numbers were not comparable with the ones
here. The BM25 run it existed for:

    python3 scripts/training/hyperparameter_tuning.py --dataset data/combine/train.jsonl --n 3000 \
        --levels 0,2,3 --sweep bm25_gain=0,2,3,4,6,8

    # ...and how much of that was BM25 vs the tokenizer repair in understand/tokens.py
    python3 scripts/training/hyperparameter_tuning.py --dataset data/combine/train.jsonl --n 3000 \
        --levels 0,2,3 --sweep bm25_gain=2,4 --legacy-tokens
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("COPILOT_OFFLINE", "1")   # fit on the offline path — a warm cache is not a run

from src.eval import harness                    # noqa: E402  harness puts the kit on sys.path

harness.load_env()                              # so a COPILOT_FLAGS you already adopted is the baseline
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


def sweep(samples, catalog: Path, levels: tuple[int, ...], spec: str, legacy: bool) -> None:
    """One flag's curve, measured by the same `objective()` the staged fit uses.

    ⚠️ Reports, fits nothing. A boundary winner is called out for the same reason it is in the
    stages: the first BM25 sweep put its optimum at the top of its own range.
    """
    from src.copilot.flags import Flags

    name, _, raw = spec.partition("=")
    current = getattr(Flags(), name)          # raises on a flag that does not exist
    cast = type(current)
    values = [cast(v) for v in raw.split(",") if v]
    assert len(values) > 1, f"--sweep needs a range, got {raw!r}"

    if legacy:
        # The original `attributes.tokens()`: a frozenset, `len > 2`, no `%`. Sorted into a list so
        # the call shape matches, but it is still a set — term frequency collapses to 1.
        import src.retrieve.bm25 as bm25_module
        from src.understand.attributes import tokens as legacy_tokens
        bm25_module.terms = lambda text: sorted(legacy_tokens(text))
        _agent(catalog).index.__dict__.pop("_bm25", None)
        print("⚠️ LEGACY TOKENIZER — pre-tokens.py surface\n")

    print(f"── sweeping {name} over {values}, levels {levels}")
    base = None
    for value in values:
        t0 = time.time()
        obj = objective(samples, catalog, levels, **{name: value})
        base = obj if base is None else base
        edge = " ⚠️ EDGE" if value in (values[0], values[-1]) else ""
        print(f"   {name:<18} {value:>6} | obj {obj:.4f}  ({obj - base:+.4f}){edge}  "
              f"[{time.time()-t0:.0f}s]", flush=True)
    print("\n⚠️ Nothing was changed, and a sweep is not an adoption — see flags.py.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default="data/train.jsonl", help="fitting set (default: data/train.jsonl)")
    ap.add_argument("--catalog", default="data/catalog.jsonl")
    ap.add_argument("--n", type=int, default=3000, help="first N sessions (0 = all). Stress is ~40x clean")
    ap.add_argument("--levels", default="0,2,3", help="paraphrase levels in the objective, 0-4")
    ap.add_argument("--output", default="runs/refit.json")
    ap.add_argument("--sweep", default="", metavar="FLAG=V1,V2,...",
                    help="sweep ONE flag through a range and stop; skips the staged fit")
    ap.add_argument("--legacy-tokens", action="store_true",
                    help="run the sweep against the pre-repair tokenizer, to price tokens.py apart "
                         "from whatever is being swept")
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

    if args.sweep:
        sweep(samples, catalog, levels, args.sweep, args.legacy_tokens)
        return

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
    adopt(chosen, inherited)


def adopt(chosen: dict, inherited: dict) -> None:
    """Print the result in both forms it can be adopted in. Changes nothing itself.

    ⚠️ The two are NOT equivalent. `.env` reaches a local runner through `Flags.from_env()`; the
    organizer constructs `Agent(catalog)` with no environment whatsoever, so a value that lives only
    in `.env` is an experiment and a value in `flags.py` is the submission. Printing only the first
    would recreate D2, where every published number came from a switch the constructed agent did not
    have.
    """
    from src.copilot.flags import Flags

    fields = Flags.__dataclass_fields__
    print("\n── to try it locally: paste into .env")
    print("COPILOT_FLAGS=" + ",".join(f"{k}={v}" for k, v in chosen.items()))
    print("\n── to SHIP it: edit src/copilot/flags.py — the evaluator passes no environment")
    for name, value in chosen.items():
        was = inherited[name]
        note = "" if value == was else f"   # was {was}"
        print(f"    {name}: {fields[name].type} = {value}{note}")
    changed = [k for k, v in chosen.items() if v != inherited[k]]
    print(f"\n⚠️ Nothing was changed. {len(changed)} of {len(chosen)} constants moved"
          f"{': ' + ', '.join(changed) if changed else ''}.")


if __name__ == "__main__":
    main()
