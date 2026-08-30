"""R4's belief — R3's posterior plus soft-card matching, and R5's BM25 term.

⚠️ `prior_damp` / `flatness()` lived here and were **removed**: they scaled the popularity prior by how
undiscriminating the evidence was, which is meaningless once `prior_weight` is 0.0 (D14) — the prior
contributes nothing to scale. `no_popularity` on the shipped configuration measures **exactly
0.000000**, which is the proof.

Kept because both earn their gain: soft-card matching (+0.0621 L2, +0.0727 L3) and BM25 (+0.0160 mean
on train, D24).
"""
from __future__ import annotations

from src.r3.belief import Belief
from src.r4.softcard import softcard_terms




class SelectiveBelief(Belief):
    """`Belief` plus the two terms that earn their gain: soft card, and BM25.

    With `soft_card_gain = 0` and `bm25_gain = 0` this reproduces `Belief` exactly, which is what keeps
    the R4-A1 and R5-A1 reduction tests meaningful.
    """

    def update(self, state, flags, semantics=None, lexical=None) -> None:
        super().update(state, flags, semantics, lexical)
        # Soft card matching runs AFTER the standard terms so it reads the same live constraints and
        # the same weights, and adds into the same log-posterior. Abstention still cancels.
        if getattr(flags, "soft_card_gain", 0.0) > 0:
            for constraint in state.live():
                weight = constraint.weight(state.turn)
                if weight <= 0:
                    continue
                for asin, log_l in softcard_terms(self.index, constraint,
                                                  self.candidates, flags).items():
                    self.log_p[asin] += weight * log_l

        # BM25 over the whole accumulated query (D24). `getattr` so R1-R4 flags, which have no such
        # field, read 0.0 and this block never runs — the R4-A1 reduction stays exact.
        bm25_gain = getattr(flags, "bm25_gain", 0.0)
        if bm25_gain > 0:
            from src.r5.bm25 import bm25_scores
            query = " ".join([state.category or ""] + [c.text for c in state.live()]).strip()
            if query:
                for asin, strength in bm25_scores(self.index, query,
                                                  self.candidates, flags).items():
                    self.log_p[asin] += bm25_gain * strength

