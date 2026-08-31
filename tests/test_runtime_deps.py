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
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT))

HEAVY = ("torch", "transformers", "sentence_transformers")
IMAGE = ("PIL", "cv2", "torchvision", "clip", "open_clip")


class TestRuntimeDependencies(unittest.TestCase):
    def test_shipped_agent_never_imports_torch(self) -> None:
        """R3-A21: the default path is numpy-only. Guarded at import time, not by inspection."""
        from src.eval import measure

        real = builtins.__import__

        def guard(name, *args, **kwargs):
            assert not name.startswith(HEAVY), f"the shipped path imported {name}"
            return real(name, *args, **kwargs)

        builtins.__import__ = guard
        try:
            agent = measure.build()
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

    def test_no_semantic_backend_exists_to_turn_on(self) -> None:
        """Four independent negatives on semantic retrieval here, so the code is gone, not gated.

        A default-off flag is a promise someone will eventually flip it; a deleted module cannot be
        flipped. The measurements survive in SUMMARY.md §3.6.
        """
        from src.copilot.flags import Flags

        self.assertNotIn("semantic_gain", vars(Flags()))
        self.assertFalse(list(SRC.rglob("semantic.py")))


if __name__ == "__main__":
    unittest.main()


class TestTheLanguageTierShipsOff(unittest.TestCase):
    """The submission makes no network call, and the switch that changes that actually works.

    `Agent.llm` is a property for exactly this reason: it used to be built in `__init__`, so a runner
    that flipped `llm_extract` on a constructed agent silently measured the tier switched OFF.
    """

    def test_the_default_agent_has_no_language_tier(self) -> None:
        from src.copilot.flags import Flags

        self.assertFalse(Flags().llm_extract, "the defaults ARE the submission — it ships offline")

    def test_flipping_the_flag_after_construction_reaches_the_builder(self) -> None:
        """`evaluate.py --llm_call` sets the flag on an agent that already exists."""
        from unittest import mock

        from src.eval import measure

        agent = measure.build()
        self.assertIsNone(agent.llm)
        agent.flags.llm_extract = True
        with mock.patch("src.understand.llm.LLMClient") as client:
            self.assertIsNotNone(agent.llm)
        self.assertEqual(client.call_count, 1)


class TestOfflineIsEnforced(unittest.TestCase):
    """The offline claim must be enforceable, not merely true on the day it was measured.

    A warm `.cache/llm` makes the default path score 0.8926 at L3 with **zero network calls** and 380
    cache hits — indistinguishable from the published offline 0.8297 unless you count cache hits. Every
    headline number is measured under `COPILOT_OFFLINE=1`; this is what makes that reproducible.
    """

    def test_offline_env_disables_the_llm_entirely(self) -> None:
        import os

        from src.eval import measure

        previous = os.environ.get("COPILOT_OFFLINE")
        os.environ["COPILOT_OFFLINE"] = "1"
        try:
            agent = measure.build()
            agent.flags.llm_extract = True   # the env must win over the flag, or the test is vacuous
            self.assertIsNone(agent.llm, "COPILOT_OFFLINE=1 must disable the LLM tier and its disk cache")
        finally:
            if previous is None:
                os.environ.pop("COPILOT_OFFLINE", None)
            else:
                os.environ["COPILOT_OFFLINE"] = previous
