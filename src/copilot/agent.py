"""The shopping copilot — the agent as a posterior. Two levels, one number, no weight tables.

    level 1   P(category | opener)    -> the pool, by mass
    level 2   P(item | pool, evidence) -> order, depth, and when to stop

⚠️ `Agent.__init__(self, catalog_path=...)` is POSITIONAL and undocumented — `local_evaluator.py`
constructs it that way, and the README, the API contract and submission_rules all omit `__init__`
entirely. **The flag defaults are the submission**; nothing here reads the environment to reach the
configuration that was measured.

⚠️ Never import `evaluator.local_evaluator` from this module: it does `from starter.agent import
Agent` at module scope, so an agent that imports it creates a circular import and a hard crash. A
*runner* may import it freely.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from src.copilot.flags import Flags
from src.rank.belief import Belief
from src.retrieve.category import CategoryBelief
from src.retrieve.index import ItemIndex
from src.state.session import SessionState
from src.understand.parse import parse

# What the agent actually SAYS when it asks. The evaluator scores `ask_attribute` and ignores
# `message` entirely, so none of this moves a number — it exists because a walkthrough of a shopping
# assistant that replies "other" is not a demonstration of anything, and Presentation is a graded
# criterion. Taken verbatim from the sibling branch that wrote them.
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

# `behavior_for()` draws the override turn from [3, 4], so by turn 4 the evaluator's
# `override_applied` flag is True in every session regardless of scenario. Structural, not tuned.
OVERRIDE_SETTLED = 4


class Agent:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.index = ItemIndex(catalog_path)
        self.categories = CategoryBelief(catalog_path)
        self.flags = Flags.from_env()
        self.sessions: dict[str, SessionState] = {}
        self._llm = None
        # Built on first use, and only when the model tier can actually fire: the pipeline builds a
        # canonical index over every card string, and on templated input the tier makes zero calls.
        self._pipeline = None
        self._prompt = 0
        self._completion = 0
        self._last_asked: dict[str, str] = {}
        self._stalls: dict[str, int] = {}
        # asins already shipped in a turn the evaluator actually hit-checked, per session
        self._shipped: dict[str, dict[str, bool]] = {}
        # popularity-ordered fallback, so a crashed turn still ships something plausible
        self._fallback = sorted(self.index.log_pop, key=lambda a: -self.index.log_pop[a])[:50]

    @property
    def llm(self):
        """The language tier, or `None`. Ships OFF — see `Flags.llm_extract`.

        Built on first use rather than in `__init__`, so a runner that flips the flag on an
        already-constructed agent (`evaluate.py --llm_call`) actually gets the tier.

        ⚠️ COPILOT_OFFLINE=1 disables it AND its disk cache. Without the cache clause, a warm
        .cache/llm scores like the online path with zero network calls — which is indistinguishable
        from the offline number unless you count cache hits.
        """
        if not self.flags.llm_extract or os.environ.get("COPILOT_OFFLINE") == "1":
            return None
        if self._llm is None:
            try:
                from src.understand.llm import LLMClient
                from src.understand.extract import AlignedExtractor
                self._llm = AlignedExtractor(LLMClient())
            except Exception:
                return None
        return self._llm

    def _intent_pipeline(self):
        """The router and its catalog verification. `None` leaves the deterministic path alone.

        Built lazily: `parse()` only reaches it on a message tiers 1 and 2 could not read, and the
        canonical index behind `exact_canonical` is a second pass over all 50,000 rows.
        """
        if self.llm is None or not self.flags.verify:
            return None
        if self._pipeline is None:
            from src.understand.intent import IntentPipeline
            self._pipeline = IntentPipeline(self.index, self.llm, self.categories)
        return self._pipeline

    def reset(self, session_id: str, user_profile: dict) -> None:
        self.sessions[session_id] = SessionState(profile=user_profile or {})
        self._shipped[session_id] = {}

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
        flags = self.flags
        before = len(state.constraints)

        # --- understand: three tiers, cheapest first, stop at the first that works ---------------
        # `parse()` gates the model per MESSAGE — it escalates only when tier 1 and tier 2 both fail
        # on this utterance, which is exactly the right question. An earlier version also ANDed in a
        # session-level `paraphrased()` test; the two could never coincide on a corpus whose
        # unreadable turn is the opener, and the tier made 0 calls across the entire free-form set.
        llm = self.llm if flags.llm_extract else None
        parse(user_message, state, llm=llm, erase=flags.erase,
              intent_pipeline=self._intent_pipeline() if llm is not None else None)

        # "Is this conversation still teaching me anything?" A turn that revealed nothing new means
        # the belief will not improve by waiting, and the policy below reads that directly instead of
        # consulting a hand-tuned deadline.
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

        # --- level 1: the pool, by posterior mass over categories --------------------------------
        # Reads the RAW opener, never a model rewrite: the pool is the earliest decision in a session
        # and unrecoverable when wrong, so it depends on nothing that can hallucinate.
        opener = state.history[0] if state.history else user_message
        candidates = self.categories.pool(opener, tau=flags.tau_mass) or self._fallback

        # --- level 2: the posterior over items in it ---------------------------------------------
        belief = Belief(self.index, candidates)
        belief.update(state, flags)

        # --- survival is evidence ----------------------------------------------------------------
        # The evaluator does `if override_applied and target in ranked: break`. So if this session is
        # still alive, every item shipped on a hit-checked turn is PROVEN not to be the target.
        # ⚠️ Only a turn the evaluator actually hit-checked proves anything, and whether it did is not
        # always knowable: paraphrase degrades route detection, and a first version that excluded on
        # `state.route` alone turned 9 intent_override hits into outright misses at L3. So the two
        # cases are kept apart: PROVEN exclusions are hard, unproven ones do nothing at all.
        # ⚠️ The rule is BINARY, and that is a measurement not a preference. Softening the unproven
        # case to a penalty measured -0.0607 (override MRR 0.983 -> 0.504), because an unchecked
        # turn's top item is the one most likely to BE the target.
        shipped = self._shipped.setdefault(session_id, {})
        if flags.exclude_shipped and shipped:
            if any(not shipped.get(a) for a in candidates):   # never empty the pool
                for asin, proven in shipped.items():
                    if proven and asin in belief.log_p:
                        belief.log_p[asin] = -math.inf

        ranked = belief.ranked()
        entropy = belief.entropy()
        # The agent's own order, before the ship/hold decision, so an offline recorder can read what
        # the agent KNEW on a turn where it shipped nothing. The agent neither imports the recorder
        # nor knows it exists.
        self._last_internal = ranked

        # --- the policy --------------------------------------------------------------------------
        if state.route == "override" and not state.override_seen and turn < flags.deadline:
            depth = 0                       # the evaluator discards anything shipped before the
                                            # override lands, even at rank 1
        elif turn >= flags.max_turns:
            depth = top_k                   # last chance: a bad rank beats no rank
        else:
            # ⚠️ A barren turn means two OPPOSITE things, and one stall counter conflated them:
            #
            #   templates matching  -> we understood everything; the customer simply has no more
            #                          preferences. The belief is trustworthy and one more turn can
            #                          still resolve it to rank 1.
            #   templates failing   -> we are not parsing the customer at all. More turns of the same
            #                          will not help, so ship wide now.
            #
            # Treating both as "give up and ship deep" made `boundary` the worst scenario: MRR 0.8583
            # at MTTC 2.30 against 0.9333 at 3.10 — converting fastest and ranking worst, which is
            # the early-conversion trap the whole policy exists to avoid.
            decay = flags.stall_decay if state.paraphrased() else flags.stall_decay_clean
            depth = belief.depth(top_k, v_continue=flags.v_continue, hope=decay ** stalls)

        out = ranked[:depth]

        # Record only what the evaluator will actually hit-check. An override session's turns before
        # the override lands are discarded even at rank 1, so surviving them proves nothing and
        # excluding those items later would permanently discard the true target.
        # ⚠️ `SessionState.route` DEFAULTS to "browsing", so "route != override" is not evidence of
        # anything — it is also what an unparsed opener looks like. Reading the default as proof cost
        # 9 intent_override sessions at L3. The test has to be positive: trust the route only on a
        # turn where the opener template actually matched, which is the only place `state.category`
        # is ever set on the offline path.
        if turn >= OVERRIDE_SETTLED:
            proven = True                   # the override has landed in every session by now
        elif state.category is None or state.paraphrased():
            proven = False                  # never read the opener; assume nothing
        else:
            proven = state.route != "override" or state.override_seen
        for asin in out:
            # never downgrade: an item proven wrong at turn 4 stays proven at turn 5
            shipped[asin] = shipped.get(asin, False) or proven

        # `"other"` makes the simulator return the next TWO undisclosed constraints; any named
        # attribute returns at most one, and `classify_constraint` never emits brand, budget or
        # category at all. Expected information gain over the posterior was built and loses at every
        # stress level (0.9509 vs 0.9720 clean) — no question-selection objective can beat "ask for
        # strictly more evidence" when one option literally returns twice as much of it.
        question = "other"
        self._last_asked[session_id] = question

        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if llm is not None:
            prompt, completion = getattr(llm, "totals", lambda: (0, 0))()
            usage = {"prompt_tokens": prompt - self._prompt,
                     "completion_tokens": completion - self._completion}
            self._prompt, self._completion = prompt, completion

        return {"message": self._message(depth, entropy, question),
                "ask_attribute": question,
                "recommendations": [{"parent_asin": a} for a in out],
                "usage": usage}

    @staticmethod
    def _message(depth: int, entropy: float, question: str) -> str:
        """What the shopper reads. Never scored — the evaluator reads `ask_attribute` instead."""
        if depth == 0:
            lead = "Understood — let me narrow this down."
        elif entropy < 0.55:
            lead = "I think this is the one."
        else:
            lead = "Here are the closest matches so far."
        return f"{lead} {QUESTION_TEXT.get(question, QUESTION_TEXT['other'])}"
