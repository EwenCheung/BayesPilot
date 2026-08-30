"""R3 — the agent as a posterior. Two levels, one number, no weight tables.

    level 1   P(category | evidence)  -> the pool, by mass
    level 2   P(item | pool, evidence) -> order, depth, and when to stop

⚠️ `Agent.__init__(self, catalog_path=...)` is POSITIONAL and undocumented — the evaluator constructs
it that way, and the README, the API contract and submission_rules all omit `__init__` entirely.
"""
from __future__ import annotations

import os
from pathlib import Path

from src.common.contracts import SessionState
from src.common.parse import parse
from src.r3.belief import Belief
from src.r3.category import CategoryBelief
from src.r3.flags import Flags
from src.r3.index import ItemIndex
from src.r3.question import best_question


class Agent:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.index = ItemIndex(catalog_path)
        self.categories = CategoryBelief(catalog_path)
        self.flags = Flags.from_env()
        self.sessions: dict[str, SessionState] = {}
        # ⚠️ R3_OFFLINE=1 disables the tier AND its disk cache. Without this, a warm .cache/llm makes
        # the default path score 0.8926 at L3 with zero network calls — which looks exactly like the
        # offline number (0.8297) unless you count cache hits. Every headline figure in
        # docs/R3-RESULTS.md §1 is measured with the tier explicitly off.
        self.llm = None
        if self.flags.llm_extract and os.environ.get("R3_OFFLINE") != "1":
            try:
                from src.common.llm import LLMClient
                self.llm = LLMClient()
            except Exception:
                self.llm = None
        self._prompt = 0
        self._completion = 0
        self._last_asked: dict[str, str] = {}
        self._stalls: dict[str, int] = {}
        self._lexical = None
        self._semantics = None
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
            if self.flags.semantic_backend == "blair":
                from src.r3.semantic import BlairSemantics
                self._semantics = BlairSemantics(self.index, query_mode=self.flags.query_mode)
            else:
                from src.r3.semantic import SvdSemantics
                self._semantics = SvdSemantics(self.index)
        return self._semantics

    def reset(self, session_id: str, user_profile: dict) -> None:
        self.sessions[session_id] = SessionState(profile=user_profile or {})

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
        state = self.sessions.setdefault(session_id, SessionState())
        state.turn = turn
        before = len(state.constraints)
        llm = self.llm if (self.flags.llm_extract and state.paraphrased()) else None
        parse(user_message, state, llm=llm, erase=self.flags.erase)
        # Pillar III, concretely: "is this conversation still teaching me anything?" A turn that
        # revealed nothing new means the belief will not improve by waiting, and the policy below
        # reads that directly instead of consulting a hand-tuned deadline.
        gained = len(state.constraints) - before
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
        opener = state.history[0] if state.history else user_message
        if self.flags.belief_pool:
            candidates = self.categories.pool(opener, tau=self.flags.tau_mass)
        else:
            candidates = self.categories.by_category[self.categories.best(opener)]
        if not candidates:
            candidates = self._fallback

        # --- level 2: the posterior over items in it ---
        # A channel-conditioned `exact_gain` (high while templates match, low once they stop) was
        # built and measured here and bought nothing — D17. It is absent rather than set to a no-op,
        # because the abstention rule in likelihood.py already does that job: a term whose evidence
        # matches nothing simply stops voting.
        flags = self.flags
        belief = Belief(self.index, candidates, use_prior=flags.prior,
                        prior_weight=flags.prior_weight,
                        pool_normalised=flags.pool_normalised_prior)
        belief.update(state, flags, self.semantics, self.lexical)
        ranked = belief.ranked()
        entropy = belief.entropy()

        # --- the policy, from one number ---
        # An override session cannot convert before the override utterance lands on turn 3-4: the
        # evaluator discards every list shipped before it, even at rank 1. So spend those turns
        # listening instead of selling. This is structural, not tuning (00-r3-spec.md §5).
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

        question = best_question(self.index, state, belief) if flags.infogain else "other"
        self._last_asked[session_id] = question
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if llm is not None:
            prompt, completion = getattr(llm, "totals", lambda: (0, 0))()
            usage = {"prompt_tokens": prompt - self._prompt,
                     "completion_tokens": completion - self._completion}
            self._prompt, self._completion = prompt, completion

        return {"message": self._message(state, depth, entropy),
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
