"""The submission entry point: R1 plus the stress wrapper the harness drives via `R1_STRESS`.

`starter/agent.py` is replaced with a three-line shim importing this class, so the graded object
is exactly the object we test.
"""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path

from src.eval.stress import paraphrase
from src.r1.agent import Agent as R1Agent


class Agent(R1Agent):
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        super().__init__(catalog_path)
        self.stress = int(os.environ.get("R1_STRESS") or 0)
        if self.stress >= 3 and self.llm is None:
            from src.common.llm import LLMClient

            self.llm = LLMClient()
        atexit.register(self._disclose)

    def _disclose(self) -> None:
        """Latency, tokens, cost and failure count are a submission requirement, and the agent runs
        in the evaluator's process — so it writes its own accounting out on the way down."""
        name = os.environ.get("R1_RUN_NAME")
        if not name or self.llm is None:
            return
        path = Path(__file__).resolve().parents[2] / "runs" / f"{name}.llm.json"
        try:
            path.write_text(json.dumps(self.llm.report(), indent=2))
        except Exception:
            pass

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        if self.stress:
            user_message = paraphrase(user_message, self.stress, llm=self.llm)
        return super().respond(session_id, user_message, turn, top_k)
