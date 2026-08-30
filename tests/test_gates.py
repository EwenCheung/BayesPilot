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
    """R2-A0: the harness reproduces two independently known numbers, without touching the kit.

    If our referee cannot reproduce the official baseline and the R1 incumbent to the digit, no number
    it reports about R2 is worth anything.
    """

    def test_a0_reproduces_official_starter_baseline(self) -> None:
        """R2-A0: pristine BM25 starter == 0.10671 (kit's own baseline_results.json)."""
        starter = load_module(ROOT / "techjam-conversational-search-main" / "starter" / "agent.py",
                              "kit_starter")
        result = harness.run(starter.Agent(str(harness.CATALOG)))
        self.assertAlmostEqual(harness.score(result), 0.10671, places=5)
        self.assertAlmostEqual(result["hit_rate_at_10"], 0.125, places=6)
        self.assertAlmostEqual(result["mttc"], 9.81, places=6)

    def test_a0_reproduces_r1_incumbent(self) -> None:
        """R2-A0: experiments/agent_best_0.9607.py == 0.9607.

        This is the shared SEED prototype, not the R1 road — R1 is developed in its own worktree. It is
        pinned here because it is a second independently-known number the harness must reproduce, which
        is all R2-A0 needs it for.
        """
        r1 = load_module(ROOT / "experiments" / "agent_best_0.9607.py", "r1_incumbent")
        result = harness.run(r1.Agent(str(harness.CATALOG)))
        self.assertAlmostEqual(harness.score(result), 0.9607, places=4)
        self.assertEqual(result["hit_rate_at_10"], 1.0)

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
