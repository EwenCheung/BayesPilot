"""Phase S — the posterior, with the prior scaled by how discriminative the evidence actually is.

**The failure this addresses, measured.** On `train.jsonl[:3000]` with `exclude_shipped` on, every
remaining failure is a ranking failure: the target is in the level-1 category pool **100% of the
time** (zero "not in pool" sessions), and the 45 misses sit at a median internal rank of **69** in a
pool of ~335.

Those sessions share a signature (00-r4-spec.md §1.3): the intent card's constraint strings are
generic — `"Department: Womens"`, `"Item Weight: 3.2 ounces"` — shared by hundreds of catalog items.
Two things then happen at once:

1. the evidence terms match most of the pool, so they are near-constant and **cancel** in the
   normalisation, exactly as `likelihood.py` intends; and
2. with the likelihoods silent, **the popularity prior decides the whole ranking** — and the missed
   targets have median `rating_number` **7** against 24 for the ones we get right.

So the prior is not merely unhelpful in this regime, it is anti-correlated with the answer. The
mechanism that carries the road on 96% of sessions is the one that buries the other 4%.

🔑 **The fix is to make the prior's weight a function of the evidence's selectivity**, not a constant.
When one constraint pins the pool to a handful of items, the prior is a tie-break and should stay
strong. When every constraint matches half the pool, the prior is the only voice in the room and
should be quieter.

⚠️ This is a *scaling*, never a removal. `no_popularity` costs R3 0.028 and R1 0.242 — the prior is
still the single most valuable signal overall, and D2's rule holds: nothing may zero anything.
"""
from __future__ import annotations

from src.r3.belief import Belief
from src.r3.likelihood import EXACT_GAIN, _bounded, constraint_terms
from src.r4.softcard import softcard_terms


def flatness(index, state, candidates: list[str], flags) -> float:
    """How undiscriminating is the live evidence, in [0, 1]?

    0.0 — some constraint isolates a handful of candidates; the evidence is sharp.
    1.0 — every constraint matches every candidate, or there is no evidence at all.

    Defined on the **most selective** constraint, not the average: one sharp constraint is enough to
    rank, and averaging lets three vague ones drown it. That mirrors the offline `ambiguity` statistic
    in 00-r4-spec.md §1.3, which used the minimum catalog frequency across the card.
    """
    if not candidates:
        return 1.0
    best = 1.0
    for constraint in state.live():
        if constraint.weight(state.turn) <= 0:
            continue
        terms = constraint_terms(index, constraint, candidates, flags)
        if not terms:                       # the term abstained: it says nothing about selectivity
            continue
        # ⚠️ NOT `log(L_MIN)`. That floor only binds when `strength * gain - gain < log(L_MIN)`,
        # which at the shipped gain of 3.2 never happens for any strength in [0, 1] — so every
        # candidate sits above it and a first version counted all 100 of 100 as matching. The real
        # no-match value is `_bounded(0, gain)`; anything strictly above it saw some evidence.
        floor = _bounded(0.0, getattr(flags, "exact_gain", EXACT_GAIN))
        matched = sum(1 for value in terms.values() if value > floor + 1e-9)
        if matched:
            best = min(best, matched / len(candidates))
    return best


class SelectiveBelief(Belief):
    """`Belief` whose prior weight is scaled by `1 - damp * flatness`.

    `damp = 0` reproduces `Belief` exactly, which is what keeps the R4-A1 reduction test meaningful.
    """

    def __init__(self, *args, damp: float = 0.0, **kwargs) -> None:
        self.damp = damp
        self.flat = 1.0
        super().__init__(*args, **kwargs)

    def update(self, state, flags, semantics=None, lexical=None) -> None:
        # Measured before the prior is rebuilt: selectivity is a property of the evidence and the
        # pool, not of the prior, so there is no circularity.
        if self.damp:
            self.flat = flatness(self.index, state, self.candidates, flags)
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

    def _prior(self) -> dict[str, float]:
        base = super()._prior()
        if not self.damp:
            return base
        scale = max(0.0, 1.0 - self.damp * self.flat)
        return {asin: value * scale for asin, value in base.items()}
