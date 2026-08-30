"""Fit `fuzzy_expand`'s three constants on `data/freeform_v1/train.jsonl`, confirm on validation.

Staged, like `scripts/fit_r4.py`: sweep one constant at a time and carry the winner forward, rather
than a full grid whose best cell is usually noise. Reports on `validation`; `test` stays for the
final number only.

    R3_OFFLINE=1 PYTHONHASHSEED=0 python3 scripts/fit_fuzzy.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "techjam-conversational-search-main"))

from evaluator.local_evaluator import evaluate  # noqa: E402
from src.eval import freeform, harness  # noqa: E402
from src.r5.agent import Agent  # noqa: E402

_, CID, CATS, PRODS = harness.load_world()


def run(samples, **over) -> float:
    agent = Agent(str(harness.CATALOG))
    agent.flags.exclude_shipped = True
    agent.flags.fuzzy_expand = bool(over)
    for name, value in over.items():
        setattr(agent.flags, name, value)
    if agent.flags.fuzzy_expand:
        from src.r5.fuzzy import FuzzyCanon
        agent._fuzzy = FuzzyCanon(agent.categories.by_category.keys(), agent.index.lexical_text)
    return harness.score(evaluate(freeform.FreeFormAgent(agent, samples), samples, CID, CATS, PRODS))


def main() -> None:
    train = freeform.split("freeform", "train")
    validation = freeform.split("freeform", "validation")

    t0 = time.time()
    base = run(train)
    print(f"train baseline (fuzzy off)          {base:.4f}   [{time.time()-t0:.0f}s]", flush=True)

    best = {"fuzzy_cutoff": 0.80, "fuzzy_k": 3, "fuzzy_min_len": 4}
    for name, grid in (("fuzzy_cutoff", (0.75, 0.80, 0.85, 0.90)),
                       ("fuzzy_k", (1, 3, 5)),
                       ("fuzzy_min_len", (3, 4, 5))):
        scores = {}
        for value in grid:
            trial = dict(best, **{name: value})
            scores[value] = run(train, **trial)
            mark = "" if scores[value] <= base else "  +"
            print(f"  {name}={value!r:<6} {scores[value]:.4f}  ({scores[value]-base:+.4f}){mark}",
                  flush=True)
        best[name] = max(scores, key=scores.get)
        print(f"  -> {name} = {best[name]!r}\n", flush=True)

    fitted = run(train, **best)
    print(f"train  fitted {best}  {fitted:.4f}  ({fitted-base:+.4f})", flush=True)

    vb, vf = run(validation), run(validation, **best)
    print(f"validation  off {vb:.4f}   fitted {vf:.4f}   ({vf-vb:+.4f})", flush=True)


if __name__ == "__main__":
    main()
