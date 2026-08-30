"""Evaluate any agent, on any dataset, at any paraphrase level, with any constant overridden.

    # the submission score — defaults only, which is the point
    python3 scripts/evaluate.py

    # one dataset, the full paraphrase ladder, with CI and per-scenario breakdown
    python3 scripts/evaluate.py \
        --agent agent:Agent \
        --catalog data/catalog.jsonl \
        --dataset data/public_set.jsonl \
        --levels 0,1,2,3,4 \
        --ci --scenarios \
        --output runs/ladder_public200.json

    # override a fitted constant, or reproduce a recorded negative
    python3 scripts/evaluate.py --dataset data/dev.jsonl --set bm25_gain=2.0
    python3 scripts/evaluate.py --dataset data/dev.jsonl --ablate no_spec_phrase

    # the four-dataset table in README.md and SUMMARY.md §3.1
    python3 scripts/evaluate.py --all --output runs/final_r5.json

⚠️ **With no flags this constructs `Agent(catalog)` and changes nothing.** That is deliberate: the
organizer constructs the agent positionally with no environment, so the defaults in
`src/copilot/flags.py` *are* the submission. A runner that hand-sets a flag the submission relies on
measures a configuration nobody will ever run — that was D2, and it invalidated every published
number until it was fixed. Every `--set` is echoed in the output so a run is self-describing.

⚠️ `COPILOT_OFFLINE=1` disables the language tier **and its disk cache**. Without it a warm
`.cache/llm` scores like the online path with zero network calls, which is indistinguishable from the
offline number unless you count cache hits.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import ablations, harness           # noqa: E402  harness puts the kit on sys.path
from evaluator.local_evaluator import evaluate    # noqa: E402  must follow harness
from src.eval import freeform                     # noqa: E402
from src.eval.stress import ParaphraseRewriter    # noqa: E402

# The three testing datasets: resplit test, freeform test, and public set.
# `wrap` swaps in the free-form opener the kit's evaluator never reads.
TABLE = (
    ("resplit_60_20_20/test", lambda: freeform.split("resplit", "test"),  False),
    ("freeform_v1/test",      lambda: freeform.split("freeform", "test"), True),
    ("public_set.jsonl",      lambda: harness.load_jsonl(ROOT / "data" / "public_set.jsonl"), False),
)


def load_agent(spec: str, catalog: str):
    """`module:Attr` or `path/to/agent.py`."""
    if spec.endswith(".py"):
        module_path = Path(spec)
        module_name = str(module_path.with_suffix("")).replace("/", ".")
        attr = "Agent"
    else:
        module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr or "Agent")(catalog)


def configure(agent, overrides: dict, ablate: tuple[str, ...]):
    if ablate:
        agent.flags = ablations.flags(*ablate)
    for key, raw in overrides.items():
        assert hasattr(agent.flags, key), f"unknown flag {key!r}"
        current = getattr(agent.flags, key)
        value = raw.lower() in ("1", "true", "yes") if isinstance(current, bool) else type(current)(raw)
        setattr(agent.flags, key, value)
    return agent


def run_one(agent, samples, level: int, wrap: bool, world) -> tuple[dict, float, float]:
    agent.sessions.clear(); agent._shipped.clear()
    agent._stalls.clear(); agent._last_asked.clear()
    subject = agent
    if wrap:
        subject = freeform.FreeFormAgent(subject, samples)
    if level:
        subject = harness.StressedAgent(subject, ParaphraseRewriter(level))
    t0 = time.time()
    result = evaluate(subject, samples, *world)
    return result, harness.score(result), time.time() - t0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", "--agent", dest="model", default="agent:Agent",
                    help="path to agent script or module:Attr (default: agent:Agent)")
    ap.add_argument("--dataset", default="data/public_set.jsonl",
                    help="path to dataset (default: data/public_set.jsonl)")
    ap.add_argument("--output", "--outputs", dest="output", default="",
                    help="path to write the evaluation output JSON")
    ap.add_argument("--catalog", default="data/catalog.jsonl")
    ap.add_argument("--levels", default="0", help="paraphrase levels, 0-4, e.g. 0,1,2,3,4")
    ap.add_argument("--limit", type=int, default=0, help="first N sessions (0 = all)")
    ap.add_argument("--set", action="append", default=[], metavar="FLAG=VALUE",
                    help="override a flag, e.g. --set bm25_gain=2.0. Repeatable")
    ap.add_argument("--ablate", default="", help=f"comma-separated: {', '.join(sorted(ablations.ABLATIONS))}")
    ap.add_argument("--ci", action="store_true", help="95%% bootstrap CI, 1,000 resamples")
    ap.add_argument("--scenarios", action="store_true", help="per-scenario breakdown")
    ap.add_argument("--all", action="store_true", help="the three-dataset table instead of --dataset")
    args = ap.parse_args()

    catalog = Path(args.catalog)
    assert catalog.exists(), f"no such catalog: {catalog} — it is 60 MB and gitignored, see README"
    overrides = dict(kv.split("=", 1) for kv in args.set)
    ablate = tuple(a.strip() for a in args.ablate.split(",") if a.strip())
    levels = tuple(int(x) for x in args.levels.split(","))

    if not harness.kit_is_pristine():
        raise SystemExit("kit drifted from its manifest — refusing to report a score")

    agent = configure(load_agent(args.model, str(catalog)), overrides, ablate)
    shown = overrides or ({"ablate": ",".join(ablate)} if ablate else "defaults only — this IS the submission")
    print(f"agent {args.model} · catalog {catalog.name} · config: {shown}\n")

    ds_path = Path(args.dataset)
    if not ds_path.exists() and (ROOT / "data" / args.dataset).exists():
        ds_path = ROOT / "data" / args.dataset
    if not ds_path.exists() and (ROOT / args.dataset).exists():
        ds_path = ROOT / args.dataset

    jobs = [(n, load(), wrap) for n, load, wrap in TABLE] if args.all else \
           [(ds_path.name, harness.load_jsonl(ds_path), "freeform" in str(ds_path))]

    rows = []
    for label, samples, wrap in jobs:
        if args.limit:
            samples = samples[:args.limit]
        harness.DATASET = ROOT / "data" / "public_set.jsonl"
        harness._CACHE.pop("world", None)
        world = harness.load_world()[1:]
        for level in levels:
            r, score, wall = run_one(agent, samples, level, wrap, world)
            calls = getattr(getattr(agent, "llm", None), "calls", 0) or 0
            row = {"dataset": label, "n": len(samples), "level": level,
                   "hit_rate_at_10": round(r["hit_rate_at_10"], 4), "mrr": round(r["mrr"], 4),
                   "mttc": round(r["mttc"], 2), "technical_score": round(score, 4),
                   "llm_calls": calls, "seconds": round(wall, 1),
                   "config": overrides or None, "ablate": list(ablate) or None}
            line = (f"{label:<24} L{level}  n={len(samples):<5} hit {r['hit_rate_at_10']:.4f}  "
                    f"mrr {r['mrr']:.4f}  mttc {r['mttc']:.2f}  score {score:.4f}")
            if args.ci:
                lo, hi = harness.bootstrap_ci(r)
                row["ci"] = [round(lo, 4), round(hi, 4)]
                line += f"  CI ({lo:.4f}, {hi:.4f})"
            print(f"{line}  calls={calls}  {wall:.0f}s", flush=True)
            if args.scenarios:
                for name in sorted(r["scenario_metrics"]):
                    m = r["scenario_metrics"][name]
                    print(f"    {name:<18} n={m['sample_count']:<5} hit {m['hit_rate_at_10']:.4f} "
                          f"mrr {m['mrr']:.4f} mttc {m['mttc']:.2f}")
                row["scenarios"] = r["scenario_metrics"]
            rows.append(row)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, indent=2))
        print(f"\n-> {out}")


if __name__ == "__main__":
    main()
