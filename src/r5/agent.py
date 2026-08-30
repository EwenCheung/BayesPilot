"""R5 — R4, plus recovery of what the free-form corpus strips out.

R4 assumed the simulator's templates. `data/freeform_v1/` does not use them: the scaffold is restyled
into slang, shorthand, typos, emoji and self-correction, so `OPENER_RE` never matches. Measured on the
400-session validation split, R4 parses the category from **0%** of openers and assigns route
"browsing" to **100%** of sessions — the dataclass default, never a decision.

R5 adds two deterministic recoveries and one escalation, in that order:

1. `CategoryMatcher` — closed-vocabulary match against the catalog's 1,115 coarse categories.
2. `route_of` — speech-act cues that survive restyling.
3. LLM canonicalisation — **only** when 1 and 2 both fail, per the fallback design.

⚠️ Every flag defaults off, so a default R5 is R4. `tests/test_r5_reduces_to_r4.py` enforces it.
"""
from __future__ import annotations

import os
from pathlib import Path

from src.r4.agent import Agent as R4Agent
from src.r5.flags import Flags
from src.r5.freetext import CategoryMatcher, reads_deterministically, route_of


class Agent(R4Agent):
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        super().__init__(catalog_path)
        self.flags = Flags.from_env()
        self._matcher = None
        self._llm_calls = 0
        self._fuzzy = None
        if self.flags.freetext_category:
            self._matcher = CategoryMatcher(self.categories.by_category.keys())
        if self.flags.fuzzy_expand:
            from src.r5.fuzzy import FuzzyCanon
            self._fuzzy = FuzzyCanon(self.categories.by_category.keys(), self.index.lexical_text)

    def _respond(self, session_id: str, user_message: str, turn: int, top_k: int):
        out = super()._respond(session_id, user_message, turn, top_k)
        return out

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        # Recovery happens BEFORE the parse tiers see the message, so the rest of the pipeline is
        # unchanged and the improvement is attributable to these two fields alone.
        # ⚠️ Fuzzy canonicalisation runs FIRST, before anything decides whether this message is
        # readable — that is the whole point: a typo'd word should get its chance to become a real
        # category word before the deterministic/LLM branch is taken. It only fires on messages the
        # deterministic path cannot already read, so a templated corpus never enters this path.
        if self._fuzzy is not None:
            try:
                if not reads_deterministically(user_message, turn):
                    user_message = self._fuzzy.expand(
                        user_message, k=self.flags.fuzzy_k, cutoff=self.flags.fuzzy_cutoff,
                        min_len=self.flags.fuzzy_min_len)
            except Exception:
                pass
        try:
            self._recover(session_id, user_message, turn)
        except Exception:
            pass
        return super().respond(session_id, user_message, turn, top_k)

    def _recover(self, session_id: str, user_message: str, turn: int) -> None:
        state = self.sessions.get(session_id)
        if state is None or not user_message:
            return
        flags = self.flags

        if flags.freetext_route and turn == 1:
            detected = route_of(user_message, default=state.route)
            if detected == "override":
                state.route = "override"
            elif detected in ("buying", "browsing"):
                state.route = detected

        # ⚠️ Only fills a category that is still unknown. Overwriting one the template tier already
        # recovered would trade an exact value for a guess.
        if flags.freetext_category and self._matcher is not None and state.category is None:
            match = self._matcher.best(user_message, floor=flags.category_floor)
            if match:
                state.category = match

        # ⚠️ R5's turn-1 LLM fallback USED TO LIVE HERE and is deliberately gone (D21). It existed
        # only to route around a broken gate in `src/r4/agent.py:51`. That gate is now repaired, so
        # `parse()` escalates per message on its own; keeping a second path here would double-call
        # every unreadable turn. `llm_fallback` is retained as a no-op flag name for one release so
        # existing run rows stay interpretable.
