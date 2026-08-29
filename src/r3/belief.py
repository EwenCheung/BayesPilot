"""Level 2 — the posterior over items, and the entropy that drives every decision.

    log P(item) = log P₀(item) + Σ_t log L(e_t | item)

`P₀` is the popularity prior. The 570x target skew is not a leak to be embarrassed about, it is a
genuine prior over which product a shopper means, and both roads measured it as the single most
valuable signal under paraphrase (R1: -0.2422 to remove it; R2 raised its weight and gained).

One number comes out — the entropy — and it answers all three questions R1 and R2 answered with
separate hand-tuned machinery: how deep to ship, whether to convert, and what to ask.
"""
from __future__ import annotations

import math

from src.r3.likelihood import constraint_terms


class Belief:
    """An unnormalised log-posterior over one candidate pool."""

    def __init__(self, index, candidates: list[str], use_prior: bool = True,
                 prior_weight: float = 0.35, pool_normalised: bool = False) -> None:
        self.index = index
        self.candidates = candidates
        self.prior_weight = prior_weight if use_prior else 0.0
        self.pool_normalised = pool_normalised
        self.log_p = self._prior()

    def _prior(self) -> dict[str, float]:
        """P₀ ∝ popularity, at a weight that keeps it commensurable with the evidence.

        ⚠️ `log1p(rating_number)` spans 0–11 across this catalog, while one exact card-string match is
        worth 3.2 in log space. Used raw as a log-prior it outvotes three exact matches, which is not a
        strong prior — it is a units error. `prior_weight` puts it on the same scale as one piece of
        evidence, and is fitted on the 140-session train split like everything else here.
        """
        if self.pool_normalised and self.candidates:
            # R2's form: "well reviewed FOR A HOOP EARRING", not "well reviewed compared to a shoe".
            # Makes prior_weight mean the same thing in a pool of watches and a pool of belts.
            top = max(self.index.log_pop[a] for a in self.candidates) or 1.0
            return {a: self.prior_weight * self.index.log_pop[a] / top for a in self.candidates}
        return {a: self.prior_weight * self.index.log_pop[a] for a in self.candidates}

    def update(self, state, flags, semantics=None, lexical=None) -> None:
        """Re-derive from the prior and all live evidence. Cheap enough, and avoids drift."""
        self.prior_weight = flags.prior_weight if flags.prior else 0.0
        self.log_p = self._prior()
        for constraint in state.live():
            weight = constraint.weight(state.turn)
            if weight <= 0:
                continue
            terms = constraint_terms(self.index, constraint, self.candidates, flags)
            for asin, log_l in terms.items():          # {} means the term abstained: nothing happens
                self.log_p[asin] += weight * log_l

        query = " ".join([state.category or ""] + [c.text for c in state.live()]).strip()
        if lexical is not None and flags.idf_gain > 0 and query:
            for asin, score in lexical.scores(query, self.candidates).items():
                self.log_p[asin] += flags.idf_gain * score

        # the semantic term reads the whole utterance history at once rather than per constraint:
        # meaning is carried by the sentence, not by the individual requirement strings
        if semantics is not None and flags.semantic_gain > 0:
            query = " ".join([state.category or ""] + [c.text for c in state.live()]).strip()
            if query:
                sims = semantics.scores(query, self.candidates)
                for asin, sim in sims.items():          # {} again means abstain
                    self.log_p[asin] += flags.semantic_gain * sim

    def normalised(self) -> dict[str, float]:
        peak = max(self.log_p.values())
        weights = {a: math.exp(v - peak) for a, v in self.log_p.items()}
        mass = sum(weights.values())
        return {a: w / mass for a, w in weights.items()}

    def ranked(self) -> list[str]:
        return sorted(self.candidates, key=lambda a: -self.log_p[a])

    def entropy(self) -> float:
        """Shannon entropy, normalised to [0, 1] by log|pool| so it is comparable across pool sizes.

        This is the number that replaces R1's NQC 0.35 and turn-3 deadline and R2's four-rung depth
        ladder and 0.60 regime threshold. A pool of 200 and a pool of 4,000 are not comparable in nats,
        and every decision here is a comparison, so the normalisation is load-bearing.
        """
        post = self.normalised()
        h = -sum(p * math.log(p) for p in post.values() if p > 0)
        ceiling = math.log(len(self.candidates)) if len(self.candidates) > 1 else 1.0
        return h / ceiling

    def depth(self, top_k: int = 10, v_continue: float = 0.90,
              turn_cost: float = 0.0667, hope: float = 1.0) -> int:
        """How many to ship, by expected utility. This replaces every gate both roads hand-tuned.

        The evaluator does `if target in ranked: best_rank = ...; break` — **any** hit ends the session
        and locks in that reciprocal rank. So shipping a long list is not free: it converts a future
        rank-1 hit into a present rank-7 one. Shipping k items is worth

            U(k) = Σ_{i≤k} p_i · (1/i)   +   (1 − Σ_{i≤k} p_i) · V

        where `V` is the reciprocal rank we expect if the session continues instead. `U(0) = V`, so
        "say nothing this turn" falls out as the k=0 case rather than being a special rule — which is
        how the override silence and R2's depth ladder both stop needing to exist.

        `turn_cost` is the real exchange rate between the scoring terms, not a knob: one extra turn
        costs 0.2 × 0.1 = 0.02 of efficiency, and MRR is weighted 0.3, so a turn is worth
        0.02 / 0.3 ≈ 0.0667 of reciprocal rank.

        ⚠️ **`V` cannot be a constant, and a first version that made it one degenerated.** With fixed
        `V`, `U(1) − U(0) = p₁(1 − V) > 0` always and `U(2) − U(1) = p₂(0.5 − V) < 0` for any V > 0.5 —
        so the agent shipped exactly one item every turn forever, scoring 0.6216 at L3 because it
        never hit and burned the whole session. Waiting is only worth something when **more evidence
        is coming**. When the customer has stopped revealing anything new (`stalled`), the belief will
        not improve, so the honest `V` is what this same list is worth — and shipping deep wins.
        """
        post = self.normalised()
        order = self.ranked()[:top_k]
        # `hope` is P(waiting still improves my answer), and it comes from the belief itself rather
        # than from a heuristic — which is the whole point of holding a posterior:
        #
        #   peaked belief (low entropy)  -> the evidence is discriminating, one more turn resolves it
        #                                   to rank 1, so be patient and ship the top 1
        #   flat belief   (high entropy) -> the evidence is not discriminating and another turn of the
        #                                   same will not change that, so every extra item is free
        #                                   upside: ship the lot
        #
        # Two earlier versions are recorded because both failed in instructive ways: a CONSTANT V made
        # `U(1) − U(0) = p₁(1 − V) > 0` and `U(2) − U(1) = p₂(0.5 − V) < 0` unconditionally, so the
        # agent shipped exactly one item every turn forever and scored 0.6216 at L3; a hard switch to
        # V = 0 on one barren turn cost 0.068 of clean MRR by panicking at a single unproductive reply.
        horizon = max(0.0, v_continue * hope - turn_cost)

        best_k, best_u, covered = 0, horizon, 0.0
        for k, asin in enumerate(order, start=1):
            covered += post[asin]
            gained = sum(post[a] / i for i, a in enumerate(order[:k], start=1))
            u = gained + (1.0 - covered) * horizon
            if u > best_u:
                best_k, best_u = k, u
        return best_k
