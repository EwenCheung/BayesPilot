"""🔵 R1 — Constraint Satisfaction. The agent is a filter (spec docs/specs/r1-constraint-satisfaction.md).

Pipeline per turn:
    parse (template → ontology → LLM)      Pillar II state tracking, slot decay, override erasure
    → survivors()                          Pillar I filter track: shrink the candidate set
    → order()                              multi-route tie-break + LLM Semantic Ranking
    → policy                               convert on convergence, else ask the highest-EIG question

⚠️ Contract notes that are easy to get wrong (IMPORTANT.md §2, §13.1):
  * `__init__` takes the catalog path positionally — the evaluator constructs `Agent(args.catalog)`
  * nothing here imports the evaluator; its logic is copied in `src/common/simulator.py`
  * one instance serves every session, so `reset` wipes session state and keeps the index
"""
from __future__ import annotations

from pathlib import Path

from src.common.catalog import CatalogIndex
from src.common.contracts import SessionState
from src.common.parse import parse
from src.r1 import policy, question, rank
from src.r1.filter import survivors
from src.r1.flags import Flags

PROFILE_BONUS = 0.5


class Agent:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.index = CatalogIndex(catalog_path)
        self.flags = Flags.from_env()
        self.sessions: dict[str, SessionState] = {}
        self.long_term: dict[str, int] = {}   # Pillar III: cross-session preference tags
        self._reported_prompt = 0
        self._reported_completion = 0
        self.llm = None
        if self.flags.llm_extract or self.flags.llm_rerank or self.flags.llm_message:
            from src.common.llm import LLMClient

            self.llm = LLMClient()
        self.dense = None
        if self.flags.dense:
            from src.common.llm import LLMClient
            from src.r1.dense import DenseRoute

            self.llm = self.llm or LLMClient()
            self.dense = DenseRoute.load(llm=self.llm)

    # --- kit interface -----------------------------------------------------
    def reset(self, session_id: str, user_profile: dict) -> None:
        profile = user_profile if isinstance(user_profile, dict) else {}
        self.sessions[session_id] = SessionState(profile=profile, long_term=dict(self.long_term))
        for tag in profile.get("preference_tags") or []:
            self.long_term[str(tag)] = self.long_term.get(str(tag), 0) + 1

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        try:
            return self._respond(session_id, user_message, turn, top_k)
        except Exception:
            # spec C3/C4 — a crash costs the turn, so always fall back to something non-empty
            return {
                "message": "Let me show you the most popular options while I refine that.",
                "ask_attribute": "other",
                "recommendations": [{"parent_asin": asin} for asin in self.index.global_pool[:top_k]],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }

    # --- the actual turn ---------------------------------------------------
    def _respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        state = self.sessions.setdefault(session_id, SessionState())
        state.turn = turn
        parse(user_message, state, llm=self.llm if self.flags.llm_extract else None, erase=self.flags.erase)
        if state.category is None or state.category not in self.index.by_category:
            # a reworded opener never matched the template — recover the pool by token overlap
            resolved = self.index.hedge(state.category or user_message) if self.flags.hedge \
                else self.index.best_category(state.category or user_message)
            if resolved:
                state.category = resolved

        candidates, scores = survivors(self.index, state, self.flags)
        if self.flags.profile:
            self._apply_profile(state, candidates, scores)
        if self.dense:
            self.dense.prepare(state, candidates)
        ranked = rank.order(self.index, state, candidates, scores, self.flags, llm=self.llm, dense=self.dense)

        show = policy.should_recommend(state, turn, ranked, scores, self.flags)
        limit = policy.truncation(ranked, scores, top_k, self.flags)
        attribute = question.best_question(self.index, state, ranked) if self.flags.infogain else "other"
        if attribute not in state.asked:
            state.asked[attribute] = True

        return {
            "message": self._message(state, ranked, attribute, show),
            "ask_attribute": attribute,
            "recommendations": [{"parent_asin": asin} for asin in ranked[:limit]] if show else [],
            "usage": self._usage(),
        }

    # --- helpers -----------------------------------------------------------
    def _apply_profile(self, state: SessionState, candidates: list[str], scores: dict[str, float]) -> None:
        """§14.6 — the personalization layer. Measured as near-information-free on this dataset
        (IMPORTANT.md §6), which is a finding worth reporting, not a reason to omit the layer."""
        tags = {str(tag).lower() for tag in state.profile.get("preference_tags") or []}
        tags |= {tag for tag, count in state.long_term.items() if count >= 3}
        if not tags:
            return
        features = self.index.pool_features(state.category)
        for asin in candidates[:500]:
            overlap = len(tags & features.tokens.get(asin, frozenset()))
            if overlap:
                scores[asin] = scores.get(asin, 0.0) + PROFILE_BONUS * overlap / len(tags)

    def _message(self, state: SessionState, ranked: list[str], attribute: str, showing: bool) -> str:
        """The simulator ignores prose entirely; the judges and the demo video do not."""
        known = len(state.live())
        if self.flags.llm_message and self.llm is not None:
            wanted = "; ".join(c.text for c in state.live())[:600]
            written = self.llm.chat(
                [{"role": "system", "content": "You are a concise shopping assistant. One or two sentences."},
                 {"role": "user", "content": f"Requirements so far: {wanted or 'none yet'}. "
                                             f"Ask the shopper about their {attribute}."}],
                max_tokens=80,
            )
            if written:
                return written
        if not showing:
            return (f"Got it — I've noted {known} requirement(s) so far. Before I recommend anything, "
                    f"what else matters to you?")
        return (f"Narrowed {len(ranked)} matching item(s) from your {state.category or 'category'} using "
                f"{known} confirmed requirement(s). Here are the closest — anything else I should weigh?")

    def _usage(self) -> dict:
        """Per-turn deltas. The evaluator SUMS this field across turns, so reporting running
        totals would over-count quadratically — and token usage is a disclosed figure."""
        if self.llm is None:
            return {"prompt_tokens": 0, "completion_tokens": 0}
        prompt = self.llm.prompt_tokens - self._reported_prompt
        completion = self.llm.completion_tokens - self._reported_completion
        self._reported_prompt = self.llm.prompt_tokens
        self._reported_completion = self.llm.completion_tokens
        return {"prompt_tokens": max(0, prompt), "completion_tokens": max(0, completion)}
