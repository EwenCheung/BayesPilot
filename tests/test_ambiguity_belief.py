from __future__ import annotations

from src.common.contracts import (
    AmbiguousConstraint,
    Constraint,
    ConstraintAlternative,
    SessionState,
)
from src.r3.belief import Belief
from src.r3.flags import Flags


class TinyIndex:
    log_pop = {"MATCH": 0.0, "MISS": 0.0}
    card = {"MATCH": ("polyester",), "MISS": ()}

    @staticmethod
    def card_pairs(asin):
        return {("material", "polyester")} if asin == "MATCH" else set()

    @staticmethod
    def pairs(asin):
        return {("material", "polyester")} if asin == "MATCH" else set()

    @staticmethod
    def tokens(asin):
        return {"polyester"} if asin == "MATCH" else set()


def _flags():
    flags = Flags()
    flags.prior = False
    flags.lexical = False
    return flags


def test_ambiguous_hypothesis_helps_without_receiving_exact_match_strength():
    index = TinyIndex()
    ambiguous_state = SessionState(turn=1)
    ambiguous_state.add_ambiguity(AmbiguousConstraint(
        evidence="poly",
        alternatives=(ConstraintAlternative("polyester", "material", "polyester", 1.0),),
        turn=1,
    ))
    ambiguous = Belief(index, ["MATCH", "MISS"], use_prior=False)
    ambiguous.update(ambiguous_state, _flags())

    exact_state = SessionState(turn=1)
    exact_state.add(Constraint("polyester", "material", "polyester", 1, "template"))
    exact = Belief(index, ["MATCH", "MISS"], use_prior=False)
    exact.update(exact_state, _flags())

    ambiguous_gap = ambiguous.log_p["MATCH"] - ambiguous.log_p["MISS"]
    exact_gap = exact.log_p["MATCH"] - exact.log_p["MISS"]
    assert 0 < ambiguous_gap < exact_gap
