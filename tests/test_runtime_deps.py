"""R3-A21 / R3-A29 — what the shipped agent is allowed to depend on.

PROBLEM.md §4.3: "organizer policy may disable network access" and multi-modal processing is out of
scope. BLaIR was built, embedded and measured (D20) and buys nothing, so torch is not a runtime
dependency — but the code that would use it still exists behind a flag, and nothing stops someone
turning it on by accident. These tests are the thing that stops it.
"""
from __future__ import annotations

import ast
import builtins
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HEAVY = ("torch", "transformers", "sentence_transformers")
IMAGE = ("PIL", "cv2", "torchvision", "clip", "open_clip")


class TestRuntimeDependencies(unittest.TestCase):
    def test_shipped_agent_never_imports_torch(self) -> None:
        """R3-A21: the default path is numpy-only. Guarded at import time, not by inspection."""
        from src.r3.agent import Agent

        real = builtins.__import__

        def guard(name, *args, **kwargs):
            assert not name.startswith(HEAVY), f"the shipped path imported {name}"
            return real(name, *args, **kwargs)

        builtins.__import__ = guard
        try:
            agent = Agent(str(ROOT / "assets" / "catalog.jsonl"))
            agent.reset("s", {})
            agent.respond("s", "I'm looking for Belts. A key requirement is: Material: leather.", 1, 10)
        finally:
            builtins.__import__ = real

    def test_no_multimodal_anywhere_under_src(self) -> None:
        """R3-A29: PROBLEM.md §4.3 puts multi-modal processing out of scope.

        The catalog carries product image URLs and CLIP-style retrieval is a natural reach. It would
        also be disqualifying, so it is a test rather than a note.
        """
        for path in (ROOT / "src").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    self.assertFalse(name.split(".")[0] in IMAGE, f"{path}: multi-modal import {name}")

    def test_semantic_term_is_off_by_default(self) -> None:
        """D19/D20: both semantic backends were measured and neither earns its place."""
        from src.r3.flags import Flags

        self.assertEqual(Flags().semantic_gain, 0.0)


if __name__ == "__main__":
    unittest.main()


class TestOfflineIsEnforced(unittest.TestCase):
    """The offline claim must be enforceable, not merely true on the day it was measured.

    A warm `.cache/llm` makes the default path score 0.8926 at L3 with **zero network calls** and 380
    cache hits — indistinguishable from the published offline 0.8297 unless you count cache hits. Every
    headline number is measured under `R3_OFFLINE=1`; this is what makes that reproducible.
    """

    def test_r3_offline_keeps_the_router_shape_but_never_calls_or_reads_cache(self) -> None:
        import os

        from src.r3.agent import Agent

        previous = os.environ.get("R3_OFFLINE")
        os.environ["R3_OFFLINE"] = "1"
        try:
            agent = Agent(str(ROOT / "assets" / "catalog.jsonl"))
            self.assertIsNotNone(agent.llm, "one submitted agent always owns the routing layer")
            agent.reset("offline-router", {})
            agent.respond(
                "offline-router",
                "I'm looking for Belts, but I'm still exploring.",
                1,
                10,
            )
            report = agent.llm.report()
            self.assertEqual(report["calls"], 0)
            self.assertEqual(report["cache_hits"], 0)
        finally:
            if previous is None:
                os.environ.pop("R3_OFFLINE", None)
            else:
                os.environ["R3_OFFLINE"] = previous
