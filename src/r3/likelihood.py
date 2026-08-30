"""The evidence terms — P(utterance | item), as bounded factors (00-r3-spec.md §3.1).

Each term scores every candidate for one kind of evidence. They are combined in log space by
`belief.py`, which is what makes them evidence rather than a weighted blend:

  🔑 **A term with no opinion cancels.** If a term assigns the same likelihood to every candidate it
  contributes a constant to every log-posterior and vanishes in the normalisation. R2 needed a
  hand-coded regime switch (`spec_support < 0.60` → load a second weight table) to stop a dominant
  popularity weight swamping routes that still had something to say. Here that switch does not exist.

  🔑 **No term may zero an item.** Every factor is bounded below by `L_MIN`. This is R1's relaxation
  rule — "an intersection that would empty S is discarded" — as arithmetic instead of a special case,
  and R1 measured what happens without it: letting soft matches delete candidates dropped Hit@10 to
  0.79 under stress, BELOW the 0.815 do-nothing baseline. The agent was deleting the target on a guess.
"""
from __future__ import annotations

import math

from src.common.attributes import tokens

L_MIN = 0.02          # floor on any single likelihood factor
EXACT_GAIN = 3.2      # log-odds an exact card-string match is worth
ATTRIBUTE_GAIN = 1.5  # a normalised (attribute, value) match — partial credit for the same evidence
LEXICAL_GAIN = 0.9    # generic token overlap; retrieval, not inversion
TOKEN_FLOOR = 0.34    # overlap below this is noise, not evidence


def _bounded(strength: float, gain: float) -> float:
    """Map a match strength in [0, 1] to a log-likelihood contribution, floored so nothing is fatal."""
    return math.log(max(L_MIN, math.exp(strength * gain) / math.exp(gain)))


def constraint_terms(index, constraint, candidates: list[str], flags) -> dict[str, float]:
    """Log-likelihood of one constraint under each candidate. Returns {} when the term abstains.

    🔑 `exact_gain` is the dial between the two roads this one fuses. Large, and an exact card-string
    match dominates everything else — the posterior collapses onto the matching set and R3 behaves like
    R1's filter. Small, and every term contributes comparably — R3 behaves like R2's scored blend.
    It is one fitted number where R1 has a shrink rule and R2 has two weight tables.
    """
    gain = getattr(flags, "exact_gain", EXACT_GAIN)
    want = tokens(constraint.text)
    out: dict[str, float] = {}
    saw_evidence = False

    for asin in candidates:
        strength = 0.0
        if flags.exact and (
            (
                constraint.tier != "llm-hypothesis"
                and constraint.text in index.card[asin]
            )
            or (
                constraint.tier.startswith("llm-canonical")
                and (constraint.attribute, constraint.value) in index.card_pairs(asin)
            )
        ):
            strength = 1.0
        elif flags.attribute and (constraint.attribute, constraint.value) in index.pairs(asin):
            strength = ATTRIBUTE_GAIN / EXACT_GAIN
        elif flags.lexical and want:
            overlap = len(want & index.tokens(asin)) / len(want)
            if overlap >= TOKEN_FLOOR:
                strength = overlap * LEXICAL_GAIN / EXACT_GAIN
        if strength:
            saw_evidence = True
        # An exclusion is the complement of positive evidence: matching candidates are penalised,
        # non-matches remain neutral. This only activates if at least one candidate actually matches.
        out[asin] = _bounded(1.0 - strength, gain) if constraint.polarity == "avoid" else _bounded(strength, gain)

    # abstain rather than flatten: a constraint nothing matches should not reshape the belief at all
    return out if saw_evidence else {}
