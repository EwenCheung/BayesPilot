"""R2 — the agent is a ranker.

    parse -> rewrite -> 4 routes -> scheduled blend -> rerank -> confidence -> ship or ask

⚠️ Never import from evaluator.local_evaluator here. It imports starter.agent at module scope, so an
agent that imports it is a circular import and a hard crash (IMPORTANT.md §13.1.1). The simulator
functions we need are copied into src/common/simulator.py and parity-tested against the kit (R2-A1).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.common.catalog import CatalogIndex  # noqa: E402
from src.common.state import SessionState, parse  # noqa: E402
from src.r2 import fusion, policy  # noqa: E402
from src.r2.routes import (  # noqa: E402
    BgeBackend, DenseRoute, LexicalRoute, PopularityRoute, Query, SpecPhraseRoute, SvdBackend,
)

ABLATIONS = ("no_popularity", "no_spec_phrase", "no_lexical", "no_dense")


class Agent:
    """The R2 ranker.

    One instance serves every session (the evaluator constructs it once), so the index and the dense
    backend are built here and amortize to zero. Session state is per-session and cleared in reset().
    """

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl", *,
                 dense: str = "auto", ablations: tuple[str, ...] = (),
                 slot_decay: float = 0.15, fuse: str = "blend",
                 use_mmr: bool = False, rerank: bool = False,
                 ladder: tuple = policy.DEPTH_LADDER, deadline: int = policy.DEADLINE,
                 schedule: dict | None = None, partial_credit: float = 0.55,
                 index: CatalogIndex | None = None, dense_backend=None,
                 lexical=None) -> None:
        # index/dense_backend/lexical are injection points for the experiment runner only: building
        # them costs ~5s and ~90s respectively, and comparing 12 variants should not pay that 12 times.
        # The evaluator constructs Agent(catalog_path) positionally and gets the plain path.
        self.index = index if index is not None else CatalogIndex(catalog_path)
        self.ablations = frozenset(ablations)
        self.slot_decay = slot_decay
        self.fuse_name = fuse
        self.ladder = ladder
        self.deadline = deadline
        self.use_mmr = use_mmr
        self.schedule = schedule or fusion.SCHEDULE
        self.llm_call_failures = 0

        self.routes: list = [
            PopularityRoute(self.index),
            SpecPhraseRoute(self.index, partial_credit),
            lexical if lexical is not None else LexicalRoute(self.index),
        ]
        self.dense_backend = dense_backend if dense_backend is not None else self._build_dense(dense)
        if self.dense_backend is not None:
            self.routes.append(DenseRoute(self.dense_backend))

        self.reranker = None
        if rerank:
            from src.r2.rerank import LlmReranker
            self.reranker = LlmReranker(self.index)

        self._sessions: dict[str, SessionState] = {}

    def _build_dense(self, mode: str):
        """auto = bge-m3 if its vectors and credentials exist, else the offline SVD backend.

        The offline path is not a courtesy: the submission may be scored with network disabled, and the
        dense route is the one route that cannot simply be skipped because it must embed the live query.
        """
        want_bge = mode in ("auto", "bge")
        have_vectors = (_ROOT / "artifacts" / "emb.npy").exists()
        have_key = bool(os.environ.get("SOCLAAS_API_KEY"))
        if want_bge and have_vectors and have_key:
            try:
                return BgeBackend(self.index)
            except Exception:
                if mode == "bge":
                    raise
        if mode == "none":
            return None
        return SvdBackend(self.index)

    def reset(self, session_id: str, user_profile: dict) -> None:
        """Wipe per-session slots. The index and backends survive; state must not leak across sessions."""
        self._sessions[session_id] = SessionState(profile=dict(user_profile or {}))

    # ---- the turn -------------------------------------------------------------------------------

    def _query(self, state: SessionState) -> Query:
        """Query rewriting: state -> the string the semantic routes actually see.

        Slot decay is applied here (PROBLEM.md §4.3): a constraint confirmed several turns ago weighs
        less than a fresh one, and an overridden one is already gone from state.
        """
        constraints = [(c.value, state.weight_of(c, self.slot_decay)) for c in state.constraints]
        category = state.resolved_category or state.category or ""
        text = category
        if constraints:
            text += ". Requirements: " + "; ".join(v for v, _ in constraints)
        return Query(
            category=state.category,
            resolved_category=state.resolved_category,
            constraints=constraints,
            text=text[:1500],
            n_slots=len(constraints),
        )

    def _rank(self, state: SessionState) -> tuple[list[str], dict[str, float]]:
        candidates = self.index.candidates(state.resolved_category)
        if not candidates:
            return [], {}
        query = self._query(state)
        scores = {route.name: route.score(query, candidates) for route in self.routes}
        weights = fusion.weights_for(query.n_slots, self.ablations, self.schedule)
        fuser = fusion.rrf if self.fuse_name == "rrf" else fusion.blend
        fused = fuser(scores, candidates, weights)
        ranked = fusion.order(fused, self.index, query)

        # Diversity only when we are genuinely uncertain and casting a wider net can help.
        if self.use_mmr and policy.confidence(fused) < 0.15:
            ranked = fusion.mmr(ranked, self.index)
        return ranked, fused

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        try:
            return self._respond(session_id, user_message, turn, top_k)
        except Exception:
            # An exception is a silently forfeited turn, so never let one escape. Fall back to the
            # popularity prior, which needs no parsing and cannot itself fail.
            fallback = self.index.candidates(None)[:top_k]
            return {
                "message": "Let me show you some popular options while I narrow this down.",
                "ask_attribute": "other",
                "recommendations": [{"parent_asin": a} for a in fallback],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }

    def _respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        state = self._sessions.get(session_id)
        if state is None:  # defensive: respond without reset
            state = self._sessions[session_id] = SessionState()

        parse(user_message, state, turn)
        if state.resolved_category is None or state.category != getattr(state, "_last_cat", None):
            state.resolved_category = self.index.resolve_category(state.category)
            state._last_cat = state.category

        ranked, fused = self._rank(state)
        conf = policy.confidence(fused)

        if self.reranker is not None and ranked and conf < 0.55:
            ranked = self.reranker.rerank(self._query(state), ranked, depth=20)
            self.llm_call_failures = self.reranker.failures

        depth = policy.depth_for(conf, turn, override_pending=not state.override_seen,
                                 ladder=self.ladder, deadline=self.deadline)
        shipped = ranked[:min(depth, top_k)]
        state.shown.extend(shipped)

        attribute = policy.next_attribute(state)
        state.asked.append(attribute)
        return {
            "message": self._message(state, conf, len(shipped)),
            "ask_attribute": attribute,
            "recommendations": [{"parent_asin": a} for a in shipped],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    def _message(self, state: SessionState, conf: float, shown: int) -> str:
        """Customer-facing prose.

        The simulator never reads this — it only reads `ask_attribute`. The judges and the demo video do
        read it, so it states what the agent actually believes rather than being decorative.
        """
        what = state.resolved_category or state.category or "something"
        if conf >= 0.55:
            return (f"I think these {what.lower()} match what you've told me. "
                    "Anything else that matters, so I can be sure?")
        if shown <= 2:
            return (f"Here's my closest guess for {what.lower()} so far — I'd rather ask than "
                    "flood you with options. What else matters to you?")
        return f"Some {what.lower()} to look at while we narrow it down. What else matters to you?"
