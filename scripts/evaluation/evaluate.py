"""Evaluate any agent, on any dataset, at any paraphrase level, with any constant overridden.

    # the submission score — defaults only, which is the point
    python3 scripts/evaluation/evaluate.py

    # evaluation for test data
    python3 scripts/evaluate.py \
    --agent agent:Agent \
    --catalog data/catalog.jsonl \
    --dataset data/final_800.jsonl \
    --offline --ci --scenarios \
    --output runs/results_final800.json

    # one dataset, the full paraphrase ladder, with CI and per-scenario breakdown
    python3 scripts/evaluation/evaluate.py \
        --agent agent:Agent \
        --catalog data/catalog.jsonl \
        --dataset data/public_set.jsonl \
        --levels 0,1,2,3,4 \
        --ci --scenarios \
        --output runs/ladder_public200.json

    # the language tier ships OFF; this switches it back on
    python3 scripts/evaluation/evaluate.py --llm_call True

    # override a fitted constant, or reproduce a recorded negative
    python3 scripts/evaluation/evaluate.py --dataset data/dev.jsonl --set bm25_gain=2.0
    python3 scripts/evaluation/evaluate.py --dataset data/dev.jsonl --ablate no_spec_phrase

    # the four-dataset table in README.md and SUMMARY.md §3.1
    python3 scripts/evaluation/evaluate.py --all --output runs/final_r5.json

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
import hashlib
import importlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.eval import ablations, harness           # noqa: E402  harness puts the kit on sys.path

harness.load_env()
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unavailable"


def provenance(catalog: Path, agent_spec: str) -> dict:
    """What FAQ §1 asks a team to retain beside the scores: the commit the run came from, proof the
    evaluator was unmodified, and enough environment detail to reproduce it."""
    kit = ROOT / "techjam-conversational-search-main" / "evaluator" / "local_evaluator.py"
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
        "agent": agent_spec,
        "evaluator_sha256": _sha256(kit),
        "catalog_sha256": _sha256(catalog),
        "kit_pristine": harness.kit_is_pristine(),
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "processor": platform.processor() or "unknown",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def llm_report(agent) -> dict:
    """The language client's own disclosure block — calls, cache hits, tokens, USD, latency.

    ⚠️ Read from the CLIENT, not from `AlignedExtractor`. The agent has two model paths: extraction
    (`understand/parse.py`) and the intent pipeline (`understand/intent.py`). Only the first touches
    `AlignedExtractor.calls`, so reading that reported **0 calls on runs that spent 85,000 tokens**.
    """
    client = getattr(agent, "llm", None)
    if client is None:
        return {}
    client = getattr(client, "client", client)          # unwrap AlignedExtractor
    report = getattr(client, "report", None)
    return report() if callable(report) else {}


REWRITER_INFO: dict = {}


def rewriter_for(level: int):
    """A rewriter for `level`. L4 gets its OWN client, and must prove it works.

    ⚠️ L4 is a property of the TEST, not of the agent: it asks a model to reword the customer, then
    measures a fully deterministic agent against the result. That is legitimate and it is the hardest
    stress we have — but it must be labelled, because two failure modes look like success:

    * `ParaphraseRewriter(4)` with no client falls through to the deterministic L3 rewrite
      (`src/eval/stress.py:138`) and reports it as L4. Verified: the deterministic L3 and L4 rewrites
      are byte-identical, so a degraded L4 is simply L3 wearing a different label.
    * a warm `.cache/llm` serves model-written text with zero network calls, so a run that looks
      offline is not.

    So the client is probed once before use, and what it did is recorded in the output.
    """
    if level < 4:
        REWRITER_INFO[level] = {"level": level, "model_written": False}
        return ParaphraseRewriter(level)
    try:
        from src.understand.llm import LLMClient
        client = LLMClient()
        probe = client.chat([{"role": "user", "content": "Reply with the single word: ok"}],
                            max_tokens=5)
        assert probe, "client returned nothing"
    except Exception as exc:
        raise SystemExit(
            f"--levels includes 4, which needs a model to WRITE the paraphrase (the agent stays "
            f"deterministic). No usable client: {exc}\n"
            f"Without one, L4 silently degrades to L3 and would be reported as L4. "
            f"Drop 4 from --levels, or provide credentials."
        )
    REWRITER_INFO[level] = {"level": 4, "model_written": True,
                            "client": getattr(client, "chat_model", "unknown")}
    REWRITER_INFO["_client"] = client
    return ParaphraseRewriter(level, llm=client)


def rewriter_info(level: int) -> dict:
    info = dict(REWRITER_INFO.get(level, {"level": level, "model_written": False}))
    client = REWRITER_INFO.get("_client")
    if info.get("model_written") and client is not None:
        info["client_calls"] = getattr(client, "calls", 0)
        info["client_cache_hits"] = getattr(client, "cache_hits", 0)
    return info


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
        subject = harness.StressedAgent(subject, rewriter_for(level))
    t0 = time.time()
    result = evaluate(subject, samples, *world)
    return result, harness.score(result), time.time() - t0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", "--agent", dest="model", default="agent:Agent",
                    help="path to agent script or module:Attr (default: agent:Agent)")
    ap.add_argument("--dataset", default="data/public_set.jsonl",
                    help="path to dataset (default: data/public_set.jsonl)")
    # ⚠️ Defaults to a real path, not "". The FAQ §1 requires retaining results.json with its
    # per-session records, and the command most likely to be run is the bare one — so the bare one
    # must leave an artifact rather than printing to a terminal nobody kept. `--output ""` opts out.
    ap.add_argument("--output", "--outputs", dest="output", default="runs/results.json",
                    help="where to write the evaluation JSON (default: runs/results.json; \"\" to skip)")
    ap.add_argument("--catalog", default="data/catalog.jsonl")
    ap.add_argument("--levels", default="0", help="paraphrase levels, 0-4, e.g. 0,1,2,3,4")
    ap.add_argument("--limit", type=int, default=0, help="first N sessions (0 = all)")
    ap.add_argument("--set", action="append", default=[], metavar="FLAG=VALUE",
                    help="override a flag, e.g. --set bm25_gain=2.0. Repeatable")
    ap.add_argument("--llm_call", nargs="?", const="true", default="",
                    help="switch the language tier on (it ships off); same as --set llm_extract=true")
    ap.add_argument("--ablate", default="", help=f"comma-separated: {', '.join(sorted(ablations.ABLATIONS))}")
    ap.add_argument("--ci", action="store_true", help="95%% bootstrap CI, 1,000 resamples")
    ap.add_argument("--scenarios", action="store_true", help="per-scenario breakdown")
    ap.add_argument("--offline", action="store_true",
                    help="force the fully deterministic path: no network, and no disk cache either")
    ap.add_argument("--no-sessions", dest="sessions", action="store_false",
                    help="omit per-session records (FAQ §1 asks that they be retained)")
    ap.add_argument("--all", action="store_true", help="the three-dataset table instead of --dataset")
    args = ap.parse_args()

    # ⚠️ Must be set BEFORE the agent is constructed — `src/copilot/agent.py:60` reads it in
    # `__init__` to decide whether to build a client at all.
    if args.offline:
        os.environ["COPILOT_OFFLINE"] = "1"

    catalog = Path(args.catalog)
    if not catalog.exists() and (ROOT / args.catalog).exists():
        catalog = ROOT / args.catalog
    assert catalog.exists(), f"no such catalog: {catalog} — it is 60 MB and gitignored, see README"
    # ⚠️ The agent got `--catalog` (via load_agent), but the EVALUATOR built its index from
    # `harness.CATALOG`, which is hardcoded. Passing a different catalog therefore scored the agent
    # against a different product set than it searched, silently, while provenance recorded the hash
    # of the one the agent used. Point both at the same file.
    harness.CATALOG = catalog
    harness._CACHE.pop("world", None)
    overrides = dict(kv.split("=", 1) for kv in args.set)
    if args.llm_call:
        overrides["llm_extract"] = args.llm_call
    ablate = tuple(a.strip() for a in args.ablate.split(",") if a.strip())
    levels = tuple(int(x) for x in args.levels.split(","))

    if not harness.kit_is_pristine():
        raise SystemExit("kit drifted from its manifest — refusing to report a score")

    agent = configure(load_agent(args.model, str(catalog)), overrides, ablate)
    # ⚠️ `COPILOT_FLAGS` in the environment (or in `.env`) silently reconfigures the agent through
    # `Flags.from_env()`. Saying "this IS the submission" over a run the environment reconfigured is
    # how D2 happened, so the header reports the environment rather than assuming it is empty.
    env_flags = os.environ.get("COPILOT_FLAGS")
    if overrides:
        shown = overrides
    elif ablate:
        shown = {"ablate": ",".join(ablate)}
    elif env_flags:
        shown = f"COPILOT_FLAGS={env_flags} — from the environment, NOT the submission defaults"
    else:
        shown = "defaults only — this IS the submission"
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
        # only the catalog-derived parts of `world` are used; samples come from `ds_path` above
        world = harness.load_world()[1:]
        for level in levels:
            r, score, wall = run_one(agent, samples, level, wrap, world)
            disclosure = llm_report(agent)
            calls = disclosure.get("calls", 0)
            failures = disclosure.get("failures", 0)
            row = {"dataset": label, "n": len(samples), "level": level,
                   "hit_rate_at_10": round(r["hit_rate_at_10"], 4), "mrr": round(r["mrr"], 4),
                   "mttc": round(r["mttc"], 2), "technical_score": round(score, 4),
                   "efficiency": round(r["efficiency"], 6),
                   "llm_calls": calls, "llm_failures": failures, "seconds": round(wall, 1),
                   "llm": disclosure or None,
                   # what generated the customer text for this level — see `rewriter_for`
                   "rewriter": rewriter_info(level),
                   # summed by the evaluator from the agent's own `usage` field
                   # (local_evaluator.py:248) — the figure FAQ §7 asks LLM systems to disclose
                   "reported_token_usage": r["reported_token_usage"],
                   "config": overrides or None, "ablate": list(ablate) or None}
            # ⚠️ The evaluator's OWN output, verbatim and unrounded. The fields above are rounded
            # for reading; these are what a reviewer should diff against a re-run. `metric_summary`,
            # `efficiency` and `recommended_technical_score` are all computed by
            # `evaluator/local_evaluator.py` — nothing here recomputes a metric.
            row["evaluator"] = {k: v for k, v in r.items() if k != "sessions"}
            if args.sessions:
                # the evaluator's own per-session records, verbatim: sample_id, scenario_type,
                # hit, first_hit_turn, best_rank, reciprocal_rank
                row["sessions"] = r["sessions"]
            line = (f"{label:<24} L{level}  n={len(samples):<5} hit {r['hit_rate_at_10']:.4f}  "
                    f"mrr {r['mrr']:.4f}  mttc {r['mttc']:.2f}  score {score:.4f}")
            if args.ci:
                lo, hi = harness.bootstrap_ci(r)
                row["ci"] = [round(lo, 4), round(hi, 4)]
                line += f"  CI ({lo:.4f}, {hi:.4f})"
            print(f"{line}  calls={calls} fails={failures}  {wall:.0f}s", flush=True)
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
        payload = {"provenance": provenance(catalog, args.model), "runs": rows}
        out.write_text(json.dumps(payload, indent=2) + "\n")
        n = sum(len(row.get("sessions", ())) for row in rows)
        print(f"\n-> {out}  ({len(rows)} run(s), {n} per-session record(s), "
              f"commit {payload['provenance']['commit'][:10]})")


if __name__ == "__main__":
    main()
