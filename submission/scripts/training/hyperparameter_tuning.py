"""Fit every tuned constant from scratch, by Bayesian optimisation, on a dataset you choose.

    python3 scripts/training/hyperparameter_tuning.py --dataset data/generated_template_set/train.jsonl --n 3000

There are **8 tuned constants** in this system and no trained weights, so this script *is* the
training pipeline. It searches the TechnicalScore itself — every objective evaluation is a full run
of the organizer's evaluator — rather than minimising a surrogate loss and hoping it transfers.

**Why not gradient descent.** TechnicalScore is computed from ranks and turn counts, both discrete.
Nudging a weight changes nothing at all until it flips a comparison inside a sort, and then the
score jumps. Measured on `generated_template_set/train.jsonl[:300]`, L0:

    exact_gain  2.9 3.0 3.1 3.2 3.3 3.4 3.5 3.6  ->  obj 0.9400 at every one of them

The objective is piecewise constant with wide flat plateaus, so the gradient is not small, it is
exactly zero, and every first-order method — SGD, Adam, finite differences, SPSA — reads that zero
and never takes a step. What this objective calls for is derivative-free search over an expensive,
noisy black box, which is what TPE (Tree-structured Parzen Estimator) is built for: it models
P(x | good trial) / P(x | bad trial) from the trials so far and samples where that ratio is highest,
so it assumes no smoothness at all.

**The noise gate is the part that matters.** 200 sessions is small and a 0.02 gap is one or two
sessions changing rank, so a search that adopts whatever scored highest is a
machine for fitting noise — the earlier staged version "improved" 7 of 8 constants on 40 sessions,
and every one of those was noise. So the search proposes and a **paired bootstrap disposes**: each
constant is re-measured alone against the incumbent over the same sessions, and only the ones whose
95% CI on the paired difference clears zero are adopted.

⚠️ **`--dataset` must be a fitting set.** Validation, public, and every `*/test` split are used for
reporting only; pointing this at one of them invalidates the held-out numbers in the README. The
script refuses.

⚠️ **This writes JSON, not code.** The fitted values are literals in `src/copilot/flags.py`; adopting
a result is a deliberate edit, so a bad fit cannot silently become the submission. The run ends by
printing both forms of the result — a `COPILOT_FLAGS=` line for `.env` to try it locally, and the
`flags.py` literals to actually ship it.

**One flag, one range** — `--sweep` replaces the search with a single parameter's curve. A former
standalone BM25 fitter duplicated `objective()` and did not set
`COPILOT_OFFLINE` and averaged its levels by hand, so its numbers were not comparable with the ones
here. The BM25 run it existed for:

    python3 scripts/training/hyperparameter_tuning.py --dataset data/generated_template_set/train.jsonl --n 3000 \
        --levels 0,2,3 --sweep bm25_gain=0,2,3,4,6,8

    # ...and how much of that was BM25 vs the tokenizer repair in understand/tokens.py
    python3 scripts/training/hyperparameter_tuning.py --dataset data/generated_template_set/train.jsonl --n 3000 \
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

# name -> (low, high). Continuous, because TPE samples rather than enumerates — the staged grid this
# replaced could only ever return a value someone had already typed into it. Ranges are deliberately
# wider than the values we ship: a winner pinned to a boundary is not a winner, and extending one of
# these ranges once reversed its own conclusion.
SPACE: dict[str, tuple[float, float]] = {
    # evidence gains — their units dominate everything downstream
    "exact_gain":        (1.0, 8.0),
    "soft_card_gain":    (0.0, 4.0),
    "soft_card_floor":   (0.15, 0.60),
    # the pool
    "tau_mass":          (0.70, 0.99),
    "temperature":       (0.5, 6.0),
    # patience
    "v_continue":        (0.40, 0.99),
    "stall_decay":       (0.01, 0.80),
    "stall_decay_clean": (0.20, 0.99),
}

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


def evaluate_on(samples, catalog: Path, level: int, **overrides) -> dict:
    """One full run of the organizer's evaluator. Returns the raw result, because the per-session
    records inside it are what the paired bootstrap resamples."""
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
        return evaluate(subject, samples, cid, cats, prods)
    finally:
        for key, value in base.items():           # never leak a trial's value into the next one
            setattr(agent.flags, key, value)


def score_on(samples, catalog: Path, level: int, **overrides) -> float:
    return harness.score(evaluate_on(samples, catalog, level, **overrides))


def objective(samples, catalog: Path, levels: tuple[int, ...], **kw) -> float:
    """Every stress level weighted equally, so a change cannot buy clean score with robustness."""
    return sum(score_on(samples, catalog, lvl, **kw) for lvl in levels) / len(levels)


def search(samples, catalog: Path, levels: tuple[int, ...], trials: int, seed: int,
           storage: str | None, incumbent: dict | None = None):
    """TPE over all 8 constants jointly. Returns the study.

    Jointly, not one at a time: the staged version fitted the evidence gains, froze them, then fitted
    the pool underneath them, so it could never see an interaction between the two. TPE conditions
    every proposal on the whole trial history.

    ⚠️ **The incumbent is enqueued as trial 0.** TPE has no notion of a starting point — its first
    `n_startup_trials` are drawn uniformly at random from `SPACE`, and it then samples where
    P(x | good) / P(x | bad) is highest. Without this, the configuration we actually ship is not in
    that history, so the search has to rediscover a known-good region by luck, and can report a
    "best" that is worse than what is already in flags.py.

    Unpromising trials are cut off part-way down the stress ladder rather than run to completion — a
    configuration already losing at L0 does not need L2 and L3 measured.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def trial_objective(trial) -> float:
        values = {name: trial.suggest_float(name, low, high) for name, (low, high) in SPACE.items()}
        total = 0.0
        for step, level in enumerate(levels):
            total += score_on(samples, catalog, level, **values)
            trial.report(total / (step + 1), step)   # median pruning compares like step with like
            if trial.should_prune():
                raise optuna.TrialPruned()
        return total / len(levels)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed, n_startup_trials=max(10, trials // 6)),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=1),
        storage=storage,
        study_name="copilot",
        load_if_exists=True,
    )

    if incumbent and not study.trials:            # not on a --resume, or it re-enqueues every run
        study.enqueue_trial(incumbent)

    t0 = time.time()

    def report(study_, trial_) -> None:
        mark = "*" if study_.best_trial.number == trial_.number else " "
        value = "pruned" if trial_.value is None else f"{trial_.value:.4f}"
        print(f"   trial {trial_.number:>3} {mark} obj {value:>6}   best {study_.best_value:.4f}"
              f"   [{time.time() - t0:.0f}s]", flush=True)

    study.optimize(trial_objective, n_trials=trials, callbacks=[report])
    return study


def confirm(samples, catalog: Path, levels: tuple[int, ...], best: dict, inherited: dict) -> dict:
    """Re-measure each proposed constant ALONE against the incumbent, and keep only what clears noise.

    ⚠️ This is the difference between a tuner and a noise amplifier. The search reports whatever
    scored highest across ~100 configurations, which on a set this size is substantially a draw from
    the sampling distribution. A constant is adopted here only if the 95% CI on the paired
    per-session difference excludes zero — a far stricter test than "its number was bigger".

    Returns {name: value} for the survivors. Everything else keeps its incumbent value.
    """
    baseline = [evaluate_on(samples, catalog, lvl) for lvl in levels]
    base_score = sum(harness.score(r) for r in baseline) / len(baseline)
    print(f"\n── confirming against the incumbent (obj {base_score:.4f}), paired bootstrap per constant")

    kept: dict[str, float] = {}
    for name, value in best.items():
        if value == inherited[name]:
            continue
        t0 = time.time()
        runs = [evaluate_on(samples, catalog, lvl, **{name: value}) for lvl in levels]
        delta = sum(harness.score(r) for r in runs) / len(runs) - base_score
        lo, hi = harness.paired_bootstrap_ci(baseline, runs)
        clears = lo > 0
        # A constant landing on a flat plateau moves NOTHING: every paired difference is exactly 0,
        # so the CI collapses to a point. Worth saying out loud rather than calling it noise — it is
        # the same flatness that rules out gradient descent, showing up per constant.
        verdict = "ADOPT" if clears else ("no effect" if lo == hi == 0 else "noise, held")
        print(f"   {name:<18} {inherited[name]:>6} → {value:<8.4g} {delta:+.4f}  "
              f"CI ({lo:+.4f}, {hi:+.4f})  {verdict}"
              f"   [{time.time() - t0:.0f}s]", flush=True)
        if clears:
            kept[name] = value
    return kept


def sweep(samples, catalog: Path, levels: tuple[int, ...], spec: str, legacy: bool) -> None:
    """One flag's curve, measured by the same `objective()` the search uses.

    ⚠️ Reports, fits nothing. A boundary winner is called out for the same reason the search reports
    one: the first BM25 sweep put its optimum at the top of its own range.
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
              f"[{time.time() - t0:.0f}s]", flush=True)
    print("\n⚠️ Nothing was changed, and a sweep is not an adoption — see flags.py.")


EVAL = ("python3 scripts/evaluation/evaluate.py --model agent.py "
        "--dataset data/public_set.jsonl --output runs/{out}.json")


def _env(values: dict) -> str:
    """The one env var `Flags.from_env()` reads. Full precision, so the command reproduces exactly
    the configuration that was measured — `runs/refit.json` carries the same numbers."""
    return "COPILOT_FLAGS=" + ",".join(f"{k}={v}" for k, v in values.items())


def adopt(chosen: dict, inherited: dict, proposed: dict | None = None) -> None:
    """Print the result in every form it can be acted on. Changes nothing itself.

    ⚠️ Trying and shipping are NOT the same act. `COPILOT_FLAGS` reaches a local runner through
    `Flags.from_env()`; the organizer constructs `Agent(catalog)` with no environment whatsoever, so
    a value that lives only in the environment is an experiment and a value in `flags.py` is the
    submission. Printing only the first would recreate D2, where every published number came from a
    switch the constructed agent did not have.
    """
    from src.copilot.flags import Flags

    fields = Flags.__dataclass_fields__
    changed = [k for k, v in chosen.items() if v != inherited[k]]

    print("\n── try it on a set you did NOT fit on — run the whole line, or keep the "
          "COPILOT_FLAGS= part in .env for the session")
    print(f"\n{_env(chosen)} \\\n    {EVAL.format(out='eval')}")
    if proposed and proposed != chosen:
        # The gate held some of the search's proposal back. Whether it was right to is itself
        # checkable: run the ungated config out of sample and see whether the gain survives.
        print("\n   ...and what the search proposed BEFORE the noise gate, to see whether the "
              "objective it won on survives out of sample:")
        print(f"\n{_env(proposed)} \\\n    {EVAL.format(out='eval_proposed')}")

    print("\n── ship it: edit src/copilot/flags.py — the evaluator passes no environment")
    for name, value in chosen.items():
        was = inherited[name]
        note = "" if value == was else f"   # was {was}"
        print(f"    {name}: {fields[name].type} = {value}{note}")
    print(f"\n⚠️ Nothing was changed. {len(changed)} of {len(chosen)} constants moved"
          f"{': ' + ', '.join(changed) if changed else ''}.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default="data/generated_template_set/train.jsonl", help="fitting set")
    ap.add_argument("--catalog", default="data/catalog.jsonl")
    ap.add_argument("--n", type=int, default=3000,
                    help="sessions per evaluation (0 = all); controls both runtime and noise floor")
    ap.add_argument("--levels", default="0,2,3", help="paraphrase levels in the objective, 0-3")
    ap.add_argument("--trials", type=int, default=60, help="TPE trials (default: 60)")
    ap.add_argument("--seed", type=int, default=0, help="sampler seed — the search is reproducible")
    ap.add_argument("--resume", default="", metavar="PATH",
                    help="sqlite study to append to, e.g. runs/tuning.db. Trials accumulate across runs")
    ap.add_argument("--output", default="runs/refit.json")
    ap.add_argument("--sweep", default="", metavar="FLAG=V1,V2,...",
                    help="sweep ONE flag through a range and stop; skips the search")
    ap.add_argument("--legacy-tokens", action="store_true",
                    help="run the sweep against the pre-repair tokenizer, to price tokens.py apart "
                         "from whatever is being swept")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    assert dataset.exists(), f"no such dataset: {dataset}"
    forbidden = ("dev.jsonl", "public_set.jsonl", "validation.jsonl", "test.jsonl")
    assert not any(dataset.name == f for f in forbidden), (
        f"{dataset.name} is a REPORTING set. Fitting on it invalidates every held-out number in "
        f"the README. Use data/generated_template_set/train.jsonl, or a split you created for fitting.")

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

    inherited = {k: getattr(Flags(), k) for k in SPACE}

    print(f"fitting on {dataset.name}[:{len(samples)}] · levels {levels} · TPE, {args.trials} trials "
          f"· seed {args.seed} · offline")
    print("⚠️ no reporting set is opened by this script\n")
    print(f"current values: {inherited}")
    t0 = time.time()
    base_obj = objective(samples, catalog, levels)
    print(f"incumbent objective {base_obj:.4f}   [{time.time() - t0:.0f}s]\n", flush=True)

    print(f"── searching {len(SPACE)} constants jointly")
    storage = None
    if args.resume:
        Path(args.resume).parent.mkdir(parents=True, exist_ok=True)
        storage = f"sqlite:///{args.resume}"
    study = search(samples, catalog, levels, args.trials, args.seed, storage, incumbent=inherited)

    print(f"\n── best trial {study.best_trial.number}: obj {study.best_value:.4f} "
          f"({study.best_value - base_obj:+.4f} vs incumbent)")
    try:
        import optuna

        importance = optuna.importance.get_param_importances(study)
        print("   which constants the score actually depends on:")
        for name, weight in importance.items():
            print(f"     {name:<18} {weight:.3f}  {'█' * round(weight * 40)}")
    except Exception as exc:                      # importance needs more than one completed trial
        importance = {}
        print(f"   (importance unavailable: {exc})")

    kept = confirm(samples, catalog, levels, study.best_params, inherited)
    chosen = dict(inherited, **kept)

    fitted_obj = objective(samples, catalog, levels, **chosen)
    print(f"\nFITTED: {chosen}")
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
        "sampler": "TPE", "trials": args.trials, "seed": args.seed,
        "inherited": inherited, "proposed": study.best_params, "fitted": chosen,
        "confirmed": sorted(kept), "importance": importance,
        "objective": {"before": round(base_obj, 4),
                      "proposed": round(study.best_value, 4),
                      "after": round(fitted_obj, 4)},
        "per_level": per_level,
    }, indent=2))
    print(f"\n-> {out}")
    adopt(chosen, inherited, study.best_params)


if __name__ == "__main__":
    main()
