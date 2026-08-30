"""R2-A5: the kit's Agent contract, including the parts no document states.

The evaluator constructs `Agent(args.catalog)` positionally. The README, submission_rules.md and
agent_api_contract.json all omit __init__ entirely (IMPORTANT.md §13.1.2), so this is the only place
that requirement is written down as an executable check.
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.simulator import ALLOWED_ATTRIBUTES  # noqa: E402
from src.r2.agent import Agent  # noqa: E402

CATALOG = ROOT / "assets" / "catalog.jsonl"


class TestAgentContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.agent = Agent(str(CATALOG), dense="none")

    def test_init_takes_catalog_path_positionally_with_a_default(self) -> None:
        """R2-A5: the evaluator does Agent(args.catalog). Get this wrong and nothing runs at all."""
        params = list(inspect.signature(Agent.__init__).parameters.values())
        self.assertEqual(params[1].name, "catalog_path")
        self.assertNotEqual(params[1].default, inspect.Parameter.empty)
        self.assertIn(params[1].kind,
                      (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY))

    def test_agent_never_imports_the_evaluator(self) -> None:
        """R2-A5: importing the evaluator from agent code is a circular import and a hard crash.

        Checked with the AST, not a substring search — these modules legitimately *discuss* the
        evaluator in their docstrings, and it is the import statement that crashes, not the word.
        """
        import ast
        for path in (ROOT / "src").rglob("*.py"):
            if "eval" in path.parts[len(ROOT.parts):]:
                continue  # harness scripts sit outside the import cycle and may import it
            for node in ast.walk(ast.parse(path.read_text())):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                self.assertFalse(
                    any("local_evaluator" in n or n == "evaluator" for n in names),
                    f"{path} imports the evaluator from agent-side code",
                )

    def test_respond_returns_a_valid_payload(self) -> None:
        """R2-A5: message is a str, ask_attribute is legal, recommendations are well-formed."""
        self.agent.reset("s1", {"preference_tags": ["fit"]})
        out = self.agent.respond("s1", "I'm looking for Belts, but I'm still exploring.", 1, 10)
        self.assertIsInstance(out["message"], str)
        self.assertTrue(out["message"].strip(), "an empty message wastes a free judged channel")
        self.assertIn(out["ask_attribute"], ALLOWED_ATTRIBUTES | {None})
        self.assertLessEqual(len(out["recommendations"]), 100)
        for rec in out["recommendations"]:
            self.assertIsInstance(rec["parent_asin"], str)
            self.assertIn(rec["parent_asin"], self.agent.index.products)

    def test_never_ships_an_empty_list(self) -> None:
        """R2-A5: top-1 weakly dominates holding, so there is never a reason to ship nothing."""
        self.agent.reset("s2", {})
        for turn, message in enumerate(
            ["I'm looking for Watches Wrist Watches, but I'm still exploring.",
             "For that, what matters is: Water Resistant.",
             "I don't have an additional preference for other."], start=1,
        ):
            out = self.agent.respond("s2", message, turn, 10)
            self.assertGreaterEqual(len(out["recommendations"]), 1, f"empty list on turn {turn}")

    def test_reset_clears_session_state(self) -> None:
        """R2-A5: one Agent serves every session, so state leaks unless reset wipes it."""
        self.agent.reset("s3", {})
        self.agent.respond("s3", "I'm looking for Belts. A key requirement is: leather.", 1, 10)
        self.assertTrue(self.agent._sessions["s3"].constraints)
        self.agent.reset("s3", {})
        self.assertEqual(self.agent._sessions["s3"].constraints, [])
        self.assertIsNone(self.agent._sessions["s3"].category)

    def test_respond_without_reset_does_not_raise(self) -> None:
        """R2-A5: an exception is a silently forfeited turn, so nothing may escape respond()."""
        out = self.agent.respond("never-reset", "I'm looking for Belts.", 1, 10)
        self.assertIsInstance(out["message"], str)
        self.assertGreaterEqual(len(out["recommendations"]), 1)

    def test_garbage_input_still_returns_a_usable_turn(self) -> None:
        """R2-A5: the fallback path must produce real catalog IDs, not an empty shrug."""
        self.agent.reset("s4", {})
        for message in ("", "?????", "\x00\x01", "a" * 5000):
            out = self.agent.respond("s4", message, 1, 10)
            self.assertIsInstance(out["message"], str)
            self.assertGreaterEqual(len(out["recommendations"]), 1)

    def test_usage_counts_are_non_negative_ints(self) -> None:
        """R2-A5: the evaluator only sums usage when both values are ints >= 0."""
        self.agent.reset("s5", {})
        usage = self.agent.respond("s5", "I'm looking for Belts.", 1, 10)["usage"]
        for key in ("prompt_tokens", "completion_tokens"):
            self.assertIsInstance(usage[key], int)
            self.assertGreaterEqual(usage[key], 0)

    def test_sessions_do_not_leak_into_each_other(self) -> None:
        """R2-A5: two interleaved sessions must not see each other's slots."""
        self.agent.reset("a", {})
        self.agent.reset("b", {})
        self.agent.respond("a", "I'm looking for Belts. A key requirement is: leather.", 1, 10)
        self.agent.respond("b", "I'm looking for Watches Wrist Watches, but I'm still exploring.", 1, 10)
        self.assertEqual(self.agent._sessions["b"].constraints, [])
        self.assertTrue(self.agent._sessions["a"].constraints)


if __name__ == "__main__":
    unittest.main()
