"""R4-A2 and R4-A4 — the barriers that keep the road's headline metric trustworthy.

R4-A4: R1, R2 and R3 are isolated from each other because a road that calls another road is not an
independent measurement. R4 is the deliberate exception — it IS R3 plus a head — so the rule is
extended rather than relaxed: `src/r4/` may import `src/r3/`, and nothing else under `src/r*/`.

R4-A2: R4's headline is an offline curve computed from ground truth. The one way that becomes a lie
is if any of it reaches the agent at runtime, so it is enforced by AST rather than by care.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

R4 = ROOT / "src" / "r4"
# Modules that exist only to score or split, and must never be reachable from agent code.
OFFLINE_ONLY = {"instrument", "devsplit", "holdout", "stress", "race", "harness", "ablations"}


def _imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class TestR4Isolation(unittest.TestCase):
    def test_r4_imports_r3_only(self) -> None:
        """R4-A4: src/r4/ may reach src/r3/, never src/r1/ or src/r2/."""
        for path in sorted(R4.rglob("*.py")):
            for module in _imported_modules(path):
                for forbidden in ("src.r1", "src.r2"):
                    self.assertFalse(
                        module == forbidden or module.startswith(forbidden + "."),
                        f"{path.name} imports {module}; lift the mechanism through R3 instead")

    def test_agent_code_never_imports_the_evaluator(self) -> None:
        """The circular-import trap: local_evaluator does `from starter.agent import Agent`."""
        for path in sorted(R4.rglob("*.py")):
            for module in _imported_modules(path):
                self.assertNotIn("local_evaluator", module,
                                 f"{path.name} imports the evaluator — circular import, hard crash")

    def test_agent_code_never_imports_offline_only_modules(self) -> None:
        """R4-A2: nothing that knows the ground truth or the split may be reachable at runtime."""
        for path in sorted(R4.rglob("*.py")):
            for module in _imported_modules(path):
                leaf = module.rsplit(".", 1)[-1]
                self.assertNotIn(leaf, OFFLINE_ONLY,
                                 f"{path.name} imports offline-only module {module}")

    def test_no_ground_truth_reaches_respond(self) -> None:
        """R4-A2: the evaluator hands `respond` four arguments and none of them is the answer."""
        from src.copilot.agent import Agent
        import inspect
        params = list(inspect.signature(Agent.respond).parameters)
        self.assertEqual(params, ["self", "session_id", "user_message", "turn", "top_k"])


if __name__ == "__main__":
    unittest.main()
