"""R5 — R4, plus BM25 as an evidence term.

R5 began as free-form recovery: category and route parsing from restyled openers, an LLM fallback, and
fuzzy spelling correction. **All four measured exactly 0.0000** and have been removed (D17, D21, D22).
What survives is the one thing that did move: BM25.

The reason free-form recovery bought nothing is worth keeping in view. The candidate pool comes from the
level-1 category posterior reading the **raw** opener, and the free-form corpus spells category words
correctly in 99.5% of openers — so there was never anything for a parser, a model or a spell-checker to
recover.

⚠️ `bm25_gain` defaults to 0.0, so a default R5 is a default R4. `tests/test_r5_reduces_to_r4.py`
enforces it.
"""
from __future__ import annotations

from pathlib import Path

from src.r4.agent import Agent as R4Agent
from src.r5.flags import Flags


class Agent(R4Agent):
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        super().__init__(catalog_path)
        self.flags = Flags.from_env()
