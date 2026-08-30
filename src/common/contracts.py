"""Spec 3 — the only structures the three roads share (IDEA.md §0.4).

Frozen: `SessionState`'s original fields. Additive: `constraints`, `asked`, `route`,
which are generic enough for R2/R3 and carry the parse result R1 filters on.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Constraint:
    """One thing the customer told us."""

    text: str                 # the raw utterance fragment, verbatim where we have it
    attribute: str            # normalised attribute name, e.g. "material"
    value: str                # normalised value, e.g. "alloy"
    turn: int                 # turn it arrived on — drives slot decay (§14.2)
    tier: str                 # which parse tier produced it: template | ontology | llm
    alive: bool = True        # an intent override retires the slot it replaces (Pillar II)
    demoted: bool = False     # retired-but-not-deleted: the shopper deprioritised it, they did
                              # not say it was false, and on this dataset it is still true of the
                              # target — deleting it outright measured -0.05 MRR on override sessions

    DEMOTED_WEIGHT = 0.35

    def weight(self, turn: int, decay: float = 0.9) -> float:
        if not self.alive:
            return 0.0
        aged = decay ** max(0, turn - self.turn)
        return aged * (self.DEMOTED_WEIGHT if self.demoted else 1.0)


@dataclass
class SessionState:
    turn: int = 0
    category: str | None = None                                  # coarse category, once known
    slots: dict[str, list[str]] = field(default_factory=dict)    # attribute -> confirmed values
    slot_age: dict[str, int] = field(default_factory=dict)       # turns since confirmed (§14.2)
    disclosed: set[str] = field(default_factory=set)             # raw constraint strings revealed
    history: list[str] = field(default_factory=list)             # customer utterances, in order
    profile: dict = field(default_factory=dict)                  # anonymized user_profile
    long_term: dict = field(default_factory=dict)                # cross-session preferences (Pillar III)

    # --- additive, shared-safe ---
    constraints: list[Constraint] = field(default_factory=list)
    asked: dict[str, bool] = field(default_factory=dict)         # attribute -> did it yield anything
    route: str = "browsing"                                      # buying | browsing | override (Pillar I)
    override_seen: bool = False                                  # the override message has arrived
    template_hits: int = 0                                       # utterances a known template matched

    def paraphrased(self) -> bool:
        """Pillar III adaptive orchestration: if nothing we know how to read has matched by the
        second turn, the wording is not what we were built for — escalate the strategy."""
        return self.turn >= 2 and self.template_hits == 0

    def add(self, constraint: Constraint) -> None:
        if any(c.text == constraint.text for c in self.constraints):
            return
        self.constraints.append(constraint)
        self.disclosed.add(constraint.text)
        self.slots.setdefault(constraint.attribute, []).append(constraint.value)
        self.slot_age[constraint.attribute] = 0

    def live(self) -> list[Constraint]:
        return [c for c in self.constraints if c.alive]
