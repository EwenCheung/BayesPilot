"""Spec 3.10 — run the official evaluator against our agent, then put the kit back exactly as it was.

A run that cannot prove the kit was pristine is not a result (IMPORTANT.md §13.1.6), so the SHA-256
of every kit file is checked before and after, and the starter is restored from a stored pristine copy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "techjam-conversational-search-main"
STARTER = KIT / "starter" / "agent.py"
PRISTINE = ROOT / "src" / "eval" / "pristine_agent.py"
MANIFEST = ROOT / "src" / "eval" / "kit_manifest.json"
GUARDED = ("evaluator/local_evaluator.py", "data/public_set.jsonl", "starter/agent.py",
           "docs/evaluation_config.json", "docs/agent_api_contract.json")

SHIM = f'''"""Submission shim — the graded Agent is src/eval/entry.py (R1 constraint satisfaction)."""
import sys
sys.path.insert(0, {str(ROOT)!r})
from src.eval.entry import Agent  # noqa: F401
'''


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest() -> dict:
    return {name: sha256(KIT / name) for name in GUARDED}


def ensure_pristine_snapshot() -> None:
    if not PRISTINE.exists():
        shutil.copy2(STARTER, PRISTINE)
    if not MANIFEST.exists():
        MANIFEST.write_text(json.dumps(manifest(), indent=2))


def verify_kit() -> None:
    expected = json.loads(MANIFEST.read_text())
    actual = manifest()
    drift = {name: (expected[name], actual[name]) for name in expected if expected[name] != actual[name]}
    if drift:
        raise SystemExit(f"kit drifted from pristine, refusing to record a run: {drift}")


def run(
    name: str,
    env: dict | None = None,
    output: Path | None = None,
    dataset: str = "train",
) -> dict:
    """Swap in our agent, run the official evaluator, restore, verify. Returns the metrics dict."""
    ensure_pristine_snapshot()
    verify_kit()
    output = output or ROOT / "runs" / f"{name}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    try:
        STARTER.write_text(SHIM)
        dataset_path = {
            "train": KIT / "data" / "resplit_60_20_20" / "train.jsonl",
            "validation": KIT / "data" / "resplit_60_20_20" / "validation.jsonl",
            "test": KIT / "data" / "resplit_60_20_20" / "test.jsonl",
            "public": KIT / "data" / "public_set.jsonl",
        }[dataset]
        process = subprocess.run(
            [sys.executable, "-m", "evaluator.local_evaluator", "--dataset", str(dataset_path),
             "--output", str(output)],
            cwd=KIT, env={**os.environ, **(env or {}), "PYTHONPATH": str(ROOT),
                          "PYTHONHASHSEED": "0", "R1_RUN_NAME": name},
            capture_output=True, text=True, timeout=7200,
        )
        if process.returncode != 0:
            raise SystemExit(f"evaluator failed:\n{process.stdout[-2000:]}\n{process.stderr[-2000:]}")
    finally:
        shutil.copy2(PRISTINE, STARTER)
    verify_kit()
    result = json.loads(output.read_text())
    result["wall_clock_s"] = round(time.time() - started, 1)
    result["variant"] = name
    result["env"] = {k: v for k, v in (env or {}).items() if k.startswith("R1_")}
    disclosure = output.parent / f"{name}.llm.json"
    result["llm"] = json.loads(disclosure.read_text()) if disclosure.exists() else {}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the official evaluator against R1")
    parser.add_argument("--name", default="r1")
    parser.add_argument("--flags", default="")
    parser.add_argument("--stress", default="0")
    parser.add_argument("--dataset", choices=("train", "validation", "test", "public"),
                        default="train")
    parser.add_argument("--acknowledge-final-test", action="store_true")
    parser.add_argument("--acknowledge-golden-final", action="store_true")
    arguments = parser.parse_args()
    if arguments.dataset == "test" and not arguments.acknowledge_final_test:
        raise SystemExit("test evaluation requires --acknowledge-final-test")
    if arguments.dataset == "public" and not arguments.acknowledge_golden_final:
        raise SystemExit("public evaluation requires --acknowledge-golden-final")
    result = run(arguments.name, {"R1_FLAGS": arguments.flags, "R1_STRESS": arguments.stress},
                 dataset=arguments.dataset)
    print(json.dumps({k: v for k, v in result.items() if k != "sessions"}, indent=2))


if __name__ == "__main__":
    main()
