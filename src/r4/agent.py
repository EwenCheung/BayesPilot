"""R4 — the agent as a scheduler. R3's posterior, a different stopping rule.

R3 answers *"which item?"*. R4 asks *"is what I have good enough to ship now?"*, because on 2,000
out-of-sample sessions the remaining loss is Efficiency (0.0332) ahead of MRR (0.0250) and Hit
(0.0152) — see 00-r4-spec.md §1.

⚠️ `_respond` is R3's loop, copied rather than called. The road's whole claim is that it differs from
R3 in a small, named set of places; calling `super()._respond()` and post-processing its output would
hide those places inside a diff nobody can read. `tests/test_r4_reduces_to_r3.py` (R4-A1) proves the
copy is faithful by requiring identical per-session rank AND turn across all 2,000 sessions with every
new flag off. If that test fails, this file has drifted and every number downstream is meaningless.
"""
from __future__ import annotations

import math
from pathlib import Path

from src.common.contracts import SessionState
from src.common.parse import parse
from src.r3.agent import Agent as R3Agent
from src.r4.belief import SelectiveBelief
from src.r3.question import best_question
from src.r4.flags import Flags


class Agent(R3Agent):
    # `behavior_for()` draws the override turn from [3, 4], so by turn 4 the evaluator's
    # `override_applied` flag is True in every session regardless of scenario. Structural, not tuned.
    OVERRIDE_SETTLED = 4

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        super().__init__(catalog_path)
        self.flags = Flags.from_env()
        # asins already shipped in a turn the evaluator actually hit-checked, per session
        self._shipped: dict[str, dict[str, bool]] = {}
        # R4 brings its own extraction prompt, aimed at the deterministic vocabulary rather than at
        # fluent English (src/r4/extract.py). The shared EXTRACT_SYSTEM stays untouched so R1/R2/R3
        # numbers do not move.
        if self.llm is not None and self.flags.aligned_extract:
            from src.r4.extract import AlignedExtractor
            self.llm = AlignedExtractor(self.llm)

    def reset(self, session_id: str, user_profile: dict) -> None:
        super().reset(session_id, user_profile)
        self._shipped[session_id] = {}

    def _respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        state = self.sessions.setdefault(session_id, SessionState())
        state.turn = turn
        before = len(state.constraints)
        # ⚠️ REPAIRED (R5 D21). This used to AND in `state.paraphrased()`, a SESSION-level test
        # (`turn >= 2 and template_hits == 0`). `parse()` already gates per message — it escalates
        # only when `not handled`, which is exactly the right question — so the extra condition was
        # a second, coarser gate that could never coincide with the first on a corpus whose
        # unreadable turn is the OPENER: turn 1 fails `turn >= 2`, and from turn 2 the templated
        # replies are `handled`. Measured: 0 extract() calls across the entire free-form corpus.
        llm = self.llm if self.flags.llm_extract else None
        parse(user_message, state, llm=llm, erase=self.flags.erase)
        gained = len(state.constraints) - before
        stalls = self._stalls.get(session_id, 0)
        stalls = stalls + 1 if (turn > 1 and gained == 0) else 0
        self._stalls[session_id] = stalls
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
        flags = self.flags
        belief = SelectiveBelief(self.index, candidates, use_prior=flags.prior,
                                 prior_weight=flags.prior_weight,
                                 pool_normalised=flags.pool_normalised_prior,
                                 damp=flags.prior_damp)
        belief.update(state, flags, self.semantics, self.lexical)

        # --- R4: survival is evidence (R4-A0 / D8) ---------------------------------------------
        # The evaluator does `if override_applied and target in ranked: break`. So if this session is
        # still alive, every item shipped on a hit-checked turn is PROVEN not to be the target, and
        # P(item | survived) = 0. R3 leaves that information on the floor and re-ships the same list.
        # ⚠️ Only a turn the evaluator actually hit-checked proves anything, and whether it did is not
        # always knowable: paraphrase degrades route detection, and a first version that excluded on
        # `state.route` alone turned 9 intent_override hits into outright misses at L3 (D9). So the
        # two cases are kept apart: PROVEN exclusions are hard, unproven ones do nothing at all.
        # ⚠️ `shipped_penalty` defaults to 0.0 deliberately. Softening the unproven case to a penalty
        # was measured WORSE than ignoring it (override MRR 0.983 -> 0.504), because an unchecked
        # turn's top item is the one most likely to BE the target. The rule has to be binary.
        shipped = self._shipped.setdefault(session_id, {})
        if flags.exclude_shipped and shipped:
            live = [a for a in candidates if not shipped.get(a)]
            if live:                      # never empty the pool; a bad rank still beats no rank
                for asin, proven in shipped.items():
                    if asin in belief.log_p:
                        belief.log_p[asin] = (-math.inf if proven
                                              else belief.log_p[asin] - flags.shipped_penalty)

        ranked = belief.ranked()
        entropy = belief.entropy()
        # The agent's own order, before the ship/hold decision. Exposed as plain state so an offline
        # recorder can read what the agent knew on a turn where it shipped nothing — the whole point
        # of FirstHit@k. The agent neither imports the recorder nor knows it exists, so the
        # offline/runtime barrier (01-contracts.md §3) holds.
        self._last_internal = ranked

        # --- the policy ---
        if state.route == "override" and not state.override_seen and turn < self.flags.deadline:
            depth = 0
        elif turn >= self.flags.max_turns:
            depth = top_k
        else:
            decay = flags.stall_decay if state.paraphrased() else flags.stall_decay_clean
            depth = belief.depth(top_k, v_continue=flags.v_continue, hope=decay ** stalls)

        out = ranked[:depth]

        # Record only what the evaluator will actually hit-check. An override session's turns before
        # the override lands are discarded even at rank 1, so surviving them proves nothing and
        # excluding those items later would permanently discard the true target.
        #
        # ⚠️ Soundness cannot rest on route detection. A first version guarded with
        # `state.route == "override"` alone and cost -0.0125 at L3 on the public set: paraphrase
        # degrades route detection, the guard silently opened, and the agent excluded items from
        # turns the evaluator had discarded. The fallback below needs no detection at all —
        # `override.turn` is drawn from {3, 4}, so `override_applied` is unconditionally True by
        # turn 4 and any list shipped from then on was certainly checked.
        # ⚠️ `SessionState.route` DEFAULTS to "browsing", so "route != override" is not evidence of
        # anything — it is also what an unparsed opener looks like. Reading the default as proof cost
        # 9 intent_override sessions at L3 (D9). The test has to be positive: we only trust the route
        # on a turn where the opener template actually matched, which is the only place
        # `state.category` is ever set on the offline path.
        if turn >= self.OVERRIDE_SETTLED:
            proven = True                        # override has landed in every session by now
        elif state.category is None or state.paraphrased():
            proven = False                       # never read the opener; assume nothing
        else:
            proven = state.route != "override" or state.override_seen
        for asin in out:
            # never downgrade: an item proven wrong at turn 4 stays proven at turn 5
            shipped[asin] = shipped.get(asin, False) or proven

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
                "recommendations": [{"parent_asin": a} for a in out],
                "usage": usage}
