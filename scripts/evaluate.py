"""Generic, model-agnostic launcher for the unchanged official evaluator.

Example:

    python scripts/evaluate.py \
      --model src/r3/agent.py \
      --test-data techjam-conversational-search-main/data/freeform_v1/test.jsonl \
      --output runs/r3_freeform_test.json

The model file must export an ``Agent`` class implementing the official contract. Passing an
explicit ``--test-data`` path is treated as authorization to evaluate that file.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "techjam-conversational-search-main"
DEFAULT_CATALOG = ROOT / "assets" / "catalog.jsonl"
EVALUATOR = KIT / "evaluator" / "local_evaluator.py"
EVALUATOR_SHA256 = "79a5ea06f9a1b8c5036f30efa85dc1f36b8f6b06eb8feb8f545dfa767bc45564"
sys.path[:0] = [str(ROOT), str(KIT)]

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from src.eval.freeform import FreeFormDatasetAgent  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_module(path: Path) -> ModuleType:
    name = f"submitted_agent_{_sha256(path)[:12]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot import model file: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module


def load_agent(path: Path, catalog: Path):
    module = _load_module(path)
    agent_class = getattr(module, "Agent", None)
    if not isinstance(agent_class, type):
        raise TypeError(f"{path} must export an Agent class")
    return agent_class(catalog)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run any Agent implementation through the unchanged official local evaluator"
    )
    parser.add_argument("--model", required=True, help="Python file exporting class Agent")
    parser.add_argument("--test-data", required=True, help="JSONL session dataset to evaluate")
    parser.add_argument("--output", required=True, help="JSON result path")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="catalog JSONL path")
    args = parser.parse_args()

    model_path = Path(args.model).expanduser().resolve()
    data_path = Path(args.test_data).expanduser().resolve()
    catalog_path = Path(args.catalog).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    for label, path in (("model", model_path), ("test data", data_path), ("catalog", catalog_path)):
        if not path.is_file():
            raise SystemExit(f"{label} file not found: {path}")

    evaluator_hash = _sha256(EVALUATOR)
    if evaluator_hash != EVALUATOR_SHA256:
        raise SystemExit("official local_evaluator.py hash changed; score rejected")

    rows = load_jsonl(data_path)
    if not rows:
        raise SystemExit("test dataset is empty")
    free_form_flags = [isinstance(row.get("free_form"), dict) for row in rows]
    if any(free_form_flags) and not all(free_form_flags):
        raise SystemExit("dataset mixes free-form and ordinary rows; split it before evaluation")

    catalog_ids, categories, products = catalog_index(catalog_path)
    agent = load_agent(model_path, catalog_path)
    subject = FreeFormDatasetAgent(agent, rows) if all(free_form_flags) else agent
    started = time.time()
    result = evaluate(subject, rows, catalog_ids, categories, products)
    result["evaluation_metadata"] = {
        "model_path": str(model_path),
        "model_sha256": _sha256(model_path),
        "test_data_path": str(data_path),
        "test_data_sha256": _sha256(data_path),
        "catalog_path": str(catalog_path),
        "catalog_sha256": _sha256(catalog_path),
        "evaluator_path": str(EVALUATOR),
        "evaluator_sha256": evaluator_hash,
        "free_form_adapter": all(free_form_flags),
        "elapsed_s": round(time.time() - started, 2),
    }
    llm = getattr(agent, "llm", None)
    if llm is not None and callable(getattr(llm, "report", None)):
        result["evaluation_metadata"]["llm"] = llm.report()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "sessions"}, indent=2))
    print(f"written: {output_path}")


if __name__ == "__main__":
    main()

