"""Re-test structural R3 choices on resplit train and validation only.

Test and public are intentionally unavailable here. Validation may confirm a decision's direction but
must not be merged back into training.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import harness, race  # noqa: E402
from evaluator.local_evaluator import evaluate  # noqa: E402
from src.eval.stress import ParaphraseRewriter  # noqa: E402


def run(split: str, stress: int = 0, **flags) -> float:
    dataset = {
        "train": harness.TRAIN_DATASET,
        "validation": harness.VALIDATION_DATASET,
    }[split]
    samples, cid, cats, prods = harness.load_world(dataset)
    agent = race.ROADS["r3"]()
    for key, value in flags.items():
        setattr(agent.flags, key, value)
    subject = harness.StressedAgent(agent, ParaphraseRewriter(stress)) if stress else agent
    return harness.score(evaluate(subject, samples, cid, cats, prods))


if __name__ == "__main__":
    print("DECISION 1 — switching EIG off")
    print(f"{'':<12s} {'train':>9s} {'validation':>11s}")
    for level in (0, 3):
        on = [run(split, level, infogain=True) for split in ("train", "validation")]
        off = [run(split, level, infogain=False) for split in ("train", "validation")]
        print(f"  L{level} EIG on  {on[0]:>9.4f} {on[1]:>11.4f}")
        print(f"  L{level} EIG off {off[0]:>9.4f} {off[1]:>11.4f}")
        print(f"  L{level} delta   {off[0]-on[0]:>+9.4f} {off[1]-on[1]:>+11.4f}", flush=True)

    print("\nDECISION 2 — dropping the BLaIR semantic term")
    for level in (0, 3):
        with_ = [
            run(split, level, semantic_gain=2.5, semantic_backend="blair")
            for split in ("train", "validation")
        ]
        without = [run(split, level, semantic_gain=0.0) for split in ("train", "validation")]
        print(
            f"  L{level} delta (without - with) "
            f"{without[0]-with_[0]:>+8.4f} {without[1]-with_[1]:>+8.4f}",
            flush=True,
        )
