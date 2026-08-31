"""Produce the retention artifact the Track 4 FAQ §1 requires.

    "Teams must retain the generated results.json, including per-session results, together with the
     submitted commit hash and relevant environment and execution details."

Writes the evaluator's own result dict verbatim — `sessions` included — plus a `provenance` block
recording the commit, the environment, and the SHA-256 of both the evaluator and the catalog, so a
reviewer can confirm the run came from the unmodified kit.

    PYTHONHASHSEED=0 python3 scripts/results_json.py [dataset.jsonl] [out.json]

⚠️ `reported_token_usage` is summed by the evaluator from the agent's own `usage` field
(`local_evaluator.py:248`). It reads 0 on a templated dataset because no model call is needed there —
that is a true zero, not a missing one. `src/common/llm.py::totals` and
`src/understand/llm.py::totals` are what make a non-zero case report honestly.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "techjam-conversational-search-main"))

from evaluator.local_evaluator import evaluate  # noqa: E402

from src.eval import harness  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unavailable"


def main() -> None:
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "public_set.jsonl"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "runs" / "results.json"

    samples, cid, cats, prods = harness.load_world()
    samples = harness.load_jsonl(dataset)

    # ⚠️ `src.copilot` is the live submission agent. `src/r4` and `src/r5` were orphaned by the
    # merge in 55b011b, which deleted `src/common/` out from under them.
    from src.copilot.agent import Agent
    agent = Agent(str(harness.CATALOG))

    started = time.time()
    result = evaluate(agent, samples, cid, cats, prods)
    elapsed = time.time() - started

    kit = ROOT / "techjam-conversational-search-main" / "evaluator" / "local_evaluator.py"
    result["provenance"] = {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "dataset": str(dataset.relative_to(ROOT)), "sessions": len(samples),
        "evaluator_sha256": sha256(kit),
        "catalog_sha256": sha256(Path(harness.CATALOG)),
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "processor": platform.processor() or "unknown",
        "elapsed_s": round(elapsed, 2),
        "ms_per_session": round(elapsed / max(1, len(samples)) * 1000, 1),
        "llm_calls": getattr(agent.llm, "calls", 0) if agent.llm is not None else 0,
        "llm_failures": getattr(agent.llm, "failures", 0) if agent.llm is not None else 0,
        "flags": {k: v for k, v in sorted(vars(agent.flags).items())},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    p = result["provenance"]
    print(f"score {result['recommended_technical_score']:.6f}  hit {result['hit_rate_at_10']:.4f}  "
          f"mrr {result['mrr']:.4f}  mttc {result['mttc']:.2f}")
    print(f"per-session records: {len(result['sessions'])}")
    print(f"reported_token_usage: {result['reported_token_usage']}")
    print(f"commit {p['commit'][:10]} dirty={p['dirty']}  evaluator {p['evaluator_sha256'][:12]}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
