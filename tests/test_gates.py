"""Score gates. These run the real evaluator and take ~10-60s each.

    python3 -m unittest tests.test_gates -v

Every reference number here was reproduced on this machine, not quoted from the docs.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import harness  # noqa: E402
from src.eval.stress import ParaphraseRewriter  # noqa: E402


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestA0HarnessCalibration(unittest.TestCase):
    """The real evaluator accepts agents on a train-derived smoke subset without touching public."""

    def test_a0_runs_official_starter_on_train(self) -> None:
        starter = load_module(ROOT / "techjam-conversational-search-main" / "starter" / "agent.py",
                              "kit_starter")
        result = harness.run(
            starter.Agent(str(harness.CATALOG)),
            dataset=harness.TRAIN_DATASET,
            sample_limit=40,
        )
        self.assertEqual(result["sample_count"], 40)

    def test_a0_runs_r3_agent_on_train(self) -> None:
        r3 = load_module(ROOT / "src" / "r3" / "agent.py", "r3_agent")
        result = harness.run(
            r3.Agent(str(harness.CATALOG)),
            dataset=harness.TRAIN_DATASET,
            sample_limit=40,
        )
        self.assertEqual(result["sample_count"], 40)

    def test_a0_kit_is_pristine(self) -> None:
        """R2-A0: the harness must never have written to the kit."""
        self.assertTrue(harness.kit_is_pristine(), "kit drifted - reported scores are unverifiable")

    def test_a0_stress_wrapper_does_not_touch_the_evaluator(self) -> None:
        """R2-A0: stress wraps the agent; the evaluator and labels are untouched."""
        seen: list[str] = []

        class Spy:
            def reset(self, session_id, user_profile): pass

            def respond(self, session_id, user_message, turn, top_k):
                seen.append(user_message)
                return {"message": "x", "ask_attribute": "other", "recommendations": []}

        wrapped = harness.StressedAgent(Spy(), ParaphraseRewriter("scaffold"))
        wrapped.respond("s", "I'm looking for Belts, but I'm still exploring.", 1, 10)
        self.assertNotIn("but I'm still exploring", seen[0])
        self.assertIn("Belts", seen[0])
        self.assertTrue(harness.kit_is_pristine())


if __name__ == "__main__":
    unittest.main()
