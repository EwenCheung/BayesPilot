"""R3 — the agent as a posterior. Two levels, one number, no weight tables.

    level 1   P(category | evidence)  -> the pool, by mass
    level 2   P(item | pool, evidence) -> order, depth, and when to stop

⚠️ `Agent.__init__(self, catalog_path=...)` is POSITIONAL and undocumented — the evaluator constructs
it that way, and the README, the API contract and submission_rules all omit `__init__` entirely.
"""
from __future__ import annotations

from pathlib import Path

from src.common.contracts import SessionState
from src.common.parse import parse
from src.r3.belief import Belief
from src.r3.category import CategoryBelief
from src.r3.flags import Flags
from src.r3.index import ItemIndex
from src.r3.question import best_question
from src.r3.rescue import (
    GlobalLexicalRescue,
    GlobalSemanticRescue,
    candidate_union,
    reciprocal_rank_fusion,
)


QUESTION_TEXT = {
    "category": "What exact type of product are you looking for?",
    "material": "Do you have a preferred material or any material you want to avoid?",
    "color": "Do you have a preferred color or pattern?",
    "size": "What size, dimensions, or fit do you need?",
    "style": "What style, cut, or level of formality do you prefer?",
    "brand": "Is there a brand you prefer or want to avoid?",
    "budget": "What budget range would you like me to stay within?",
    "feature": "What must-have feature or compatibility requirement matters most?",
    "use_case": "What occasion, activity, environment, or season is this for?",
    "other": "What other requirement matters most to your decision?",
}


class Agent:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.index = ItemIndex(catalog_path)
        self.categories = CategoryBelief(catalog_path)
        self.flags = Flags.from_env()
        self.sessions: dict[str, SessionState] = {}
        # One submitted agent always owns the router. R3_OFFLINE remains an evaluation/failure
        # safeguard inside LLMClient, not a selectable agent feature; production attempts one routing
        # call per message and deterministically falls back when the endpoint cannot answer.
        self.llm = None
        try:
            from src.common.llm import LLMClient
            self.llm = LLMClient()
        except Exception:
            self.llm = None
        self.intent_pipeline = None
        if self.llm is not None:
            from src.common.intent import IntentPipeline
            self.intent_pipeline = IntentPipeline(self.index, self.llm, self.categories)
        self._prompt = 0
        self._completion = 0
        self._last_asked: dict[str, str] = {}
        self._stalls: dict[str, int] = {}
        self._lexical = None
        self._semantics = None
        self._global_lexical: GlobalLexicalRescue | None = None
        self._global_semantic: GlobalSemanticRescue | None = None
        # popularity-ordered fallback, so a crashed turn still ships something plausible
        self._fallback = sorted(self.index.log_pop, key=lambda a: -self.index.log_pop[a])[:50]

    @property
    def lexical(self):
        """Built on first use, not in __init__ — flags may be set after construction by the
        experiment runner, and an optional stage that silently never builds looks exactly like an
        optional stage that makes no difference."""
        if self._lexical is None and self.flags.idf_gain > 0:
            from src.r3.lexical import IdfLexical
            self._lexical = IdfLexical(self.index)
        return self._lexical

    @property
    def semantics(self):
        if self._semantics is None and self.flags.semantic_gain > 0:
            if getattr(self.flags, "semantic_backend", "svd") == "blair":
                try:
                    from src.r3.semantic import BlairSemantics
                    self._semantics = BlairSemantics(self.index, query_mode=getattr(self.flags, "query_mode", "model"))
                except Exception:
                    from src.r3.semantic import SvdSemantics
                    self._semantics = SvdSemantics(self.index)
            else:
                from src.r3.semantic import SvdSemantics
                self._semantics = SvdSemantics(self.index)
        return self._semantics

    @property
    def global_lexical(self):
        """Built on first use, only when lexical rescue is enabled."""
        if self._global_lexical is None and getattr(self.flags, "rescue_lexical", False):
            self._global_lexical = GlobalLexicalRescue(self.index)
        return self._global_lexical

    @property
    def global_semantic(self):
        """Built on first use, only when semantic rescue is enabled. Reuses the in-pool backend."""
        if self._global_semantic is None and (
            getattr(self.flags, "rescue_semantic", False) or getattr(self.flags, "rescue_normalized", False)
        ):
            # Force semantics to build if not already done (we need the embeddings)
            if self._semantics is None:
                backend = getattr(self.flags, "semantic_backend", "svd")
                if backend == "blair":
                    try:
                        from src.r3.semantic import BlairSemantics
                        self._semantics = BlairSemantics(self.index, query_mode=getattr(self.flags, "query_mode", "model"))
                    except Exception:
                        from src.r3.semantic import SvdSemantics
                        self._semantics = SvdSemantics(self.index)
                else:
                    from src.r3.semantic import SvdSemantics
                    self._semantics = SvdSemantics(self.index)
            if self._semantics is not None:
                self._global_semantic = GlobalSemanticRescue(self._semantics)
        return self._global_semantic

    def reset(self, session_id: str, user_profile: dict) -> None:
        self.sessions[session_id] = SessionState(profile=user_profile or {})

    def _ensure_intent_pipeline(self) -> None:
        """Keep the single submitted router available; failure falls back inside the parser."""
        if self.llm is None:
            try:
                from src.common.llm import LLMClient
                self.llm = LLMClient()
            except Exception:
                return
        if self.intent_pipeline is None:
            from src.common.intent import IntentPipeline
            self.intent_pipeline = IntentPipeline(self.index, self.llm, self.categories)

    def _candidate_pool(self, state: SessionState, user_message: str) -> list[str]:
        """Rebuild retrieval from the catalog-backed category index on every turn.

        When rescue flags are enabled, the pool is the UNION of:
          C_category ∪ TopK_lexical(q_raw) ∪ TopK_semantic(q_raw) ∪ TopK_semantic(q_norm)
        """
        opener = (
            state.category
            or state.category_surface
            or state.restored_messages.get(1)
            or (state.history[0] if state.history else user_message)
        )
        if self.flags.belief_pool:
            cat_pool = self.categories.pool(opener, tau=self.flags.tau_mass)
        else:
            cat_pool = self.categories.by_category[self.categories.best(opener)]
        cat_pool = list(cat_pool) if cat_pool else list(self._fallback)

        flags = self.flags
        rescue_lex = getattr(flags, "rescue_lexical", False)
        rescue_sem = getattr(flags, "rescue_semantic", False)
        rescue_norm = getattr(flags, "rescue_normalized", False)
        rescue_top_k = getattr(flags, "rescue_top_k", 200)

        any_rescue = rescue_lex or rescue_sem or rescue_norm
        if not any_rescue:
            return cat_pool

        # Build the query from all accumulated evidence
        query_raw = " ".join(
            [state.category or state.category_surface or ""]
            + list(state.history)
        ).strip() or user_message

        rescue_results: list[list[tuple[str, float]]] = []
        cat_set = set(cat_pool)

        # RAWLEX: global IDF/BM25 rescue
        if rescue_lex and self.global_lexical is not None:
            rescue_results.append(
                self.global_lexical.rescue(query_raw, top_k=rescue_top_k, exclude=cat_set)
            )

        # RAWSEM: global semantic rescue from raw text
        if rescue_sem and self.global_semantic is not None:
            rescue_results.append(
                self.global_semantic.rescue(query_raw, top_k=rescue_top_k, exclude=cat_set)
            )

        # NORMSEM: global semantic rescue from LLM-normalized text
        if rescue_norm and self.global_semantic is not None:
            normalized_query = " ".join(
                state.normalized_messages.values()
            ).strip()
            if normalized_query and normalized_query != query_raw:
                rescue_results.append(
                    self.global_semantic.rescue(normalized_query, top_k=rescue_top_k, exclude=cat_set)
                )

        # UNION: merge category pool + all rescue candidates
        return candidate_union(cat_pool, rescue_results)

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        try:
            return self._respond(session_id, user_message, turn, top_k)
        except Exception:
            # a crash costs the turn; ship the prior rather than nothing
            return {"message": "Let me show you some popular options while I refine that.",
                    "ask_attribute": "other",
                    "recommendations": [{"parent_asin": a} for a in self._fallback[:top_k]],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    def _respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        self._ensure_intent_pipeline()
        state = self.sessions.setdefault(session_id, SessionState())
        state.turn = turn
        before = len(state.constraints) + len(state.ambiguities)
        parse(
            user_message,
            state,
            erase=getattr(self.flags, "erase", "demote"),
            intent_pipeline=self.intent_pipeline,
        )
        # Pillar III, concretely: "is this conversation still teaching me anything?" A turn that
        # revealed nothing new means the belief will not improve by waiting, and the policy below
        # reads that directly instead of consulting a hand-tuned deadline.
        gained = len(state.constraints) + len(state.ambiguities) - before
        stalls = self._stalls.get(session_id, 0)
        stalls = stalls + 1 if (turn > 1 and gained == 0) else 0
        self._stalls[session_id] = stalls
        # An attribute the customer had nothing to say about is dead for the rest of the session.
        # Without this the agent re-asks it every turn: measured, it burned turns 4-10 of a session
        # on "feature is up to you" and cost ~1.5 turns of MTTC at L3.
        previous = self._last_asked.get(session_id)
        if turn > 1 and previous and gained == 0:
            state.asked[previous] = False

        # --- level 1: the pool, by posterior mass over categories ---
        candidates = self._candidate_pool(state, user_message)

        # --- level 2: the posterior over items in it ---
        # A channel-conditioned `exact_gain` (high while templates match, low once they stop) was
        # built and measured here and bought nothing — D17. It is absent rather than set to a no-op,
        # because the abstention rule in likelihood.py already does that job: a term whose evidence
        # matches nothing simply stops voting.
        flags = self.flags
        belief = Belief(self.index, candidates, use_prior=getattr(flags, "prior", True),
                        prior_weight=getattr(flags, "prior_weight", 0.10),
                        pool_normalised=getattr(flags, "pool_normalised_prior", False))
        belief.update(state, flags, self.semantics, self.lexical)
        entropy = belief.entropy()

        # --- optional RRF fusion across routes ---
        use_rrf = getattr(flags, "use_rrf", False)
        rescue_lex = getattr(flags, "rescue_lexical", False)
        rescue_sem = getattr(flags, "rescue_semantic", False)
        rescue_norm = getattr(flags, "rescue_normalized", False)
        rescue_top_k = getattr(flags, "rescue_top_k", 200)

        if use_rrf and (rescue_lex or rescue_sem or rescue_norm):
            ranked_lists: dict[str, list[str]] = {}
            rrf_weights: dict[str, float] = {}

            # Route 1: Bayesian posterior (always present)
            ranked_lists["bayesian"] = belief.ranked()
            rrf_weights["bayesian"] = getattr(flags, "rrf_weight_category", 1.0)

            # Route 2: Global lexical rescue ranking
            query_raw = " ".join(
                [state.category or state.category_surface or ""]
                + list(state.history)
            ).strip() or user_message
            if rescue_lex and self.global_lexical is not None:
                lex_results = self.global_lexical.rescue(query_raw, top_k=rescue_top_k)
                if lex_results:
                    ranked_lists["lexical"] = [a for a, _ in lex_results]
                    rrf_weights["lexical"] = getattr(flags, "rrf_weight_lexical", 0.5)

            # Route 3: Global semantic rescue ranking (raw + normalized)
            if rescue_sem and self.global_semantic is not None:
                sem_results = self.global_semantic.rescue(query_raw, top_k=rescue_top_k)
                if sem_results:
                    ranked_lists["semantic_raw"] = [a for a, _ in sem_results]
                    rrf_weights["semantic_raw"] = getattr(flags, "rrf_weight_semantic", 0.5)

            if rescue_norm and self.global_semantic is not None:
                normalized_query = " ".join(state.normalized_messages.values()).strip()
                if normalized_query:
                    sem_norm = self.global_semantic.rescue(normalized_query, top_k=rescue_top_k)
                    if sem_norm:
                        ranked_lists["semantic_norm"] = [a for a, _ in sem_norm]
                        rrf_weights["semantic_norm"] = getattr(flags, "rrf_weight_semantic", 0.5)

            ranked = reciprocal_rank_fusion(ranked_lists, rrf_weights, k=getattr(flags, "rrf_k", 60))
        else:
            ranked = belief.ranked()

        # --- the policy, from one number ---
        # An override session cannot convert before the override lands: the evaluator discards every
        # list shipped before it, even at rank 1. Structural, not tuning (00-r3-spec.md §5).
        if state.route == "override" and not state.override_seen and turn < self.flags.deadline:
            depth = 0
        elif turn >= self.flags.max_turns:
            depth = top_k                       # last chance: a bad rank beats no rank
        else:
            # ⚠️ A barren turn means two OPPOSITE things, and one stall counter conflated them:
            #
            #   templates matching  -> we understood everything; the customer simply has no more
            #                          preferences ("I don't have a preference for X"). Our belief is
            #                          trustworthy and one more turn can still resolve it to rank 1.
            #   templates failing   -> we are not parsing the customer at all. More turns of the same
            #                          will not help, so ship wide now.
            #
            # Treating both as "give up and ship deep" made boundary sessions the worst scenario in
            # R3 (MRR 0.8583 at MTTC 2.30, against R1's 0.9333 at 3.10) — converting fastest and
            # ranking worst, which is the early-conversion trap the whole policy exists to avoid.
            decay = flags.stall_decay if state.paraphrased() else flags.stall_decay_clean
            depth = belief.depth(top_k, v_continue=flags.v_continue, hope=decay ** stalls)

        if flags.critical_questions:
            question = best_question(self.index, state, belief, include_other=False)
        elif flags.infogain:
            question = best_question(self.index, state, belief, include_other=True)
        else:
            question = "other"
        message = QUESTION_TEXT.get(question, QUESTION_TEXT["other"])
        self._last_asked[session_id] = question
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if self.llm is not None:
            prompt, completion = getattr(self.llm, "totals", lambda: (0, 0))()
            usage = {"prompt_tokens": prompt - self._prompt,
                     "completion_tokens": completion - self._completion}
            self._prompt, self._completion = prompt, completion

        return {"message": message,
                "ask_attribute": question,
                "recommendations": [{"parent_asin": a} for a in ranked[:depth]],
                "usage": usage}

    @staticmethod
    def _message(state: SessionState, depth: int, entropy: float) -> str:
        if depth == 0:
            return "Understood — tell me a little more and I will narrow this down."
        if entropy < 0.55:
            return "I think this is the one. Does it look right?"
        return "Here are the closest matches so far — what else matters to you?"
