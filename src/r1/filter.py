"""Spec 3.6 — the shrinking candidate set. This is what makes R1 R1.

`S` starts as the stated category and is intersected once per live constraint. An intersection
that would empty `S` is discarded instead (relaxation), because an empty set forfeits the turn
and a wrong-but-non-empty set still has the target in it more often than not.
"""
from __future__ import annotations

from src.common.attributes import tokens
from src.common.catalog import CatalogIndex
from src.common.contracts import Constraint, SessionState
from src.r1.flags import Flags

# precision-ordered: shrink on the sharp matchers first, so relaxation only ever widens
TOKEN_OVERLAP = 0.6


def _matches(constraint: Constraint, asin: str, features, flags: Flags) -> float:
    """Return match strength in [0, 1]: 1.0 exact, 0.6 attribute, 0.3 token overlap, 0 none."""
    if flags.spec_phrase and constraint.text in features.phrases.get(asin, ()):
        return 1.0
    if flags.attribute and (constraint.attribute, constraint.value) in features.pairs.get(asin, ()):
        return 0.6
    if flags.token:
        wanted = tokens(constraint.text)
        if wanted:
            overlap = len(wanted & features.tokens.get(asin, frozenset())) / len(wanted)
            if overlap >= TOKEN_OVERLAP:
                return 0.3
    return 0.0


def survivors(index: CatalogIndex, state: SessionState, flags: Flags) -> tuple[list[str], dict[str, float]]:
    """Return (candidate set, weighted match score per candidate). Never empty (spec 3.6)."""
    features = index.pool_features(state.category)
    candidates = list(features.asins)
    scores: dict[str, float] = {asin: 0.0 for asin in candidates}

    for constraint in sorted(state.live(), key=lambda c: -c.weight(state.turn)):
        weight = constraint.weight(state.turn)
        if weight <= 0:
            continue
        hits = {}
        for asin in candidates:
            strength = _matches(constraint, asin, features, flags)
            if strength:
                hits[asin] = strength
        for asin, strength in hits.items():
            scores[asin] += weight * strength
        # Shrink only on evidence sharp enough to trust. A fuzzy match that removes products is
        # worse than no match at all: under paraphrase stress, shrinking on attribute-level hits
        # dropped hit@10 below the popularity-only baseline — the agent was filtering the target
        # out on the strength of a guess. Weak matchers still contribute score, they just do not
        # get to delete anything.
        if hits and len(hits) < len(candidates) and max(hits.values()) >= flags.shrink_min:
            candidates = [asin for asin in candidates if asin in hits]
    return candidates, scores
