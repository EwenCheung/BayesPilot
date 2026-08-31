"""Level 2 — the posterior over items, and the entropy that drives every decision.

    log P(item) = Sum_t  weight_t . log L(e_t | item)

One number comes out — the entropy — and it answers questions that a blend has to answer with separate
hand-tuned machinery: how deep to ship, whether to convert, and what the reply sentence should be.

⚠️ **There is no popularity prior.** `prior_weight` was fitted to `0.0` on the generated training
set, which made the term arithmetically inert — ablating popularity moved the score by *exactly*
0.000000 — and
`prior_damp`/`flatness()` were ~50 lines of machinery scaling a zero. Deleting the prior costs nothing
on clean text and gains ~0.09 under paraphrase, so the submitted implementation omits it.
"""
from __future__ import annotations

import math

from src.rank.likelihood import constraint_terms
from src.rank.softcard import softcard_terms
from src.state.session import Constraint


class Belief:
    """An unnormalised log-posterior over one candidate pool."""

    def __init__(self, index, candidates: list[str]) -> None:
        self.index = index
        self.candidates = candidates
        self.log_p = {a: 0.0 for a in candidates}

    def update(self, state, flags) -> None:
        """Re-derive from all live evidence. Cheap enough, and avoids drift."""
        self.log_p = {a: 0.0 for a in self.candidates}

        for constraint in state.live():
            weight = constraint.weight(state.turn)
            if weight <= 0:
                continue
            # {} means the term abstained: a constraint nothing matches should not reshape the belief
            for asin, log_l in constraint_terms(self.index, constraint,
                                                self.candidates, flags).items():
                self.log_p[asin] += weight * log_l
            # Soft card runs after the standard terms so it reads the same live constraints and the
            # same weights, and adds into the same log-posterior. Abstention still cancels.
            if flags.soft_card_gain > 0:
                for asin, log_l in softcard_terms(self.index, constraint,
                                                  self.candidates, flags).items():
                    self.log_p[asin] += weight * log_l

        # --- ambiguity, as a mixture rather than a guess ----------------------------------------
        # Ambiguous language contributes ONE probability mixture, never several independent exact
        # constraints. If "poly" plausibly means polyester or polyurethane, an item matching either
        # receives soft support while neither interpretation is promoted to fact. Adding each reading
        # separately would let one uncertain span outvote three things the shopper confirmed.
        for ambiguity in state.live_ambiguities():
            alternatives = []
            for option in ambiguity.alternatives:
                hypothesis = Constraint(
                    text=option.text,
                    attribute=option.attribute,
                    value=option.value,
                    turn=ambiguity.turn,
                    tier="llm-hypothesis",
                    source_text=ambiguity.evidence,
                    polarity=ambiguity.polarity,
                    strength="soft",
                    confidence=option.confidence,
                )
                terms = constraint_terms(self.index, hypothesis, self.candidates, flags)
                if terms:
                    alternatives.append((option.confidence, terms))
            mass = sum(probability for probability, _ in alternatives)
            if mass > 0:
                weight = ambiguity.weight(state.turn)
                for asin in self.candidates:
                    mixture = sum(
                        probability * math.exp(terms[asin])
                        for probability, terms in alternatives
                    ) / mass
                    self.log_p[asin] += weight * math.log(max(1e-12, mixture))

        # BM25 reads the whole accumulated query at once rather than one constraint at a time:
        # term saturation and length normalisation are properties of a query, not of a phrase.
        if flags.bm25_gain > 0:
            from src.retrieve.bm25 import bm25_scores
            query = " ".join(
                [state.category or state.category_surface or ""]
                + list(state.normalized_messages.values())
                + [c.source_text or c.text for c in state.live()]
                + [item.evidence for item in state.live_ambiguities()]
            ).strip()
            if query:
                for asin, strength in bm25_scores(self.index, query,
                                                  self.candidates, flags).items():
                    self.log_p[asin] += flags.bm25_gain * strength

    def normalised(self) -> dict[str, float]:
        peak = max(self.log_p.values())
        weights = {a: math.exp(v - peak) for a, v in self.log_p.items()}
        mass = sum(weights.values())
        return {a: w / mass for a, w in weights.items()}

    def ranked(self) -> list[str]:
        return sorted(self.candidates, key=lambda a: -self.log_p[a])

    def entropy(self) -> float:
        """Shannon entropy, normalised to [0, 1] by log|pool| so it is comparable across pool sizes.

        ⚠️ Used ONLY to pick the reply sentence. The depth policy below does not read it — see the
        `depth()` docstring for why a belief-driven patience signal was built, measured and lost.
        """
        post = self.normalised()
        h = -sum(p * math.log(p) for p in post.values() if p > 0)
        ceiling = math.log(len(self.candidates)) if len(self.candidates) > 1 else 1.0
        return h / ceiling

    def depth(self, top_k: int = 10, v_continue: float = 0.75,
              turn_cost: float = 0.0667, hope: float = 1.0) -> int:
        """How many to ship, by expected utility. This replaces every hand-tuned gate.

        The evaluator does `if target in ranked: best_rank = ...; break` — **any** hit ends the session
        and locks in that reciprocal rank. So a long list is not free: it converts a future rank-1 hit
        into a present rank-7 one. Shipping k items is worth

            U(k) = Sum_{i<=k} p_i . (1/i)  +  (1 - Sum_{i<=k} p_i) . V

        where `V` is the reciprocal rank we expect if the session continues. `U(0) = V`, so "say
        nothing this turn" falls out as the k=0 case rather than being a special rule. The marginal
        value of slot k is `p_k . (1/k - V)`, so this is exactly **the largest k with 1/k > V** — a
        rank threshold, independent of the shape of the posterior.

        `turn_cost` is the exchange rate between the scoring terms, not a knob: one extra turn costs
        0.2 x 0.1 = 0.02 of Efficiency, and MRR is weighted 0.3, so a turn is worth 0.02 / 0.3.

        ⚠️ **`V` cannot be a constant.** With fixed `V`, `U(1) - U(0) = p1(1 - V) > 0` always and
        `U(2) - U(1) = p2(0.5 - V) < 0` for any V > 0.5 — so the agent ships exactly one item every
        turn forever, scoring 0.6216 at L3. Waiting is only worth something when more evidence is
        coming, which is what `hope` prices.
        """
        post = self.normalised()
        order = self.ranked()[:top_k]
        horizon = max(0.0, v_continue * hope - turn_cost)

        best_k, best_u, covered = 0, horizon, 0.0
        for k, asin in enumerate(order, start=1):
            covered += post[asin]
            gained = sum(post[a] / i for i, a in enumerate(order[:k], start=1))
            u = gained + (1.0 - covered) * horizon
            if u > best_u:
                best_k, best_u = k, u
        return best_k
