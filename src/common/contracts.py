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
    source_text: str | None = None  # original evidence when ``text`` is a verified canonical label
    polarity: str = "require"       # require | avoid
    strength: str = "hard"          # hard | soft
    confidence: float = 1.0
    superseded_turn: int | None = None

    DEMOTED_WEIGHT = 0.35

    def weight(self, turn: int, decay: float = 0.9) -> float:
        if not self.alive:
            return 0.0
        aged = decay ** max(0, turn - self.turn)
        strength_weight = 0.70 if self.strength == "soft" else 1.0
        return aged * strength_weight * self.confidence * (
            self.DEMOTED_WEIGHT if self.demoted else 1.0
        )


@dataclass(frozen=True)
class ConstraintAlternative:
    """One catalog-supported interpretation of an ambiguous evidence span."""

    text: str
    attribute: str
    value: str
    confidence: float


@dataclass
class AmbiguousConstraint:
    """Evidence that is useful but not safe enough for an exact constraint."""

    evidence: str
    alternatives: tuple[ConstraintAlternative, ...]
    turn: int
    polarity: str = "require"
    strength: str = "soft"
    alive: bool = True

    def weight(self, current_turn: int, decay: float = 0.9) -> float:
        if not self.alive:
            return 0.0
        strength_weight = 0.70 if self.strength == "soft" else 1.0
        return decay ** max(0, current_turn - self.turn) * strength_weight


@dataclass
class SessionState:
    turn: int = 0
    category: str | None = None                                  # coarse category, once known
    category_surface: str | None = None                          # shopper wording when canonical is ambiguous
    category_hypotheses: list[tuple[str, float]] = field(default_factory=list)
    slots: dict[str, list[str]] = field(default_factory=dict)    # attribute -> confirmed values
    slot_age: dict[str, int] = field(default_factory=dict)       # turns since confirmed (§14.2)
    disclosed: set[str] = field(default_factory=set)             # raw constraint strings revealed
    history: list[str] = field(default_factory=list)             # customer utterances, in order
    restored_messages: dict[int, str] = field(default_factory=dict)  # verified fixed-template form
    profile: dict = field(default_factory=dict)                  # anonymized user_profile
    long_term: dict = field(default_factory=dict)                # cross-session preferences (Pillar III)

    # --- additive, shared-safe ---
    constraints: list[Constraint] = field(default_factory=list)
    ambiguities: list[AmbiguousConstraint] = field(default_factory=list)
    exclusions: dict[str, list[str]] = field(default_factory=dict)  # attribute -> values to avoid
    asked: dict[str, bool] = field(default_factory=dict)         # attribute -> did it yield anything
    route: str = "browsing"                                      # buying | browsing | override (Pillar I)
    override_seen: bool = False                                  # the override message has arrived
    template_hits: int = 0                                       # utterances a known template matched
    llm_restoration_hits: int = 0                                # unknown surfaces safely classified

    def paraphrased(self) -> bool:
        """Pillar III adaptive orchestration: if nothing we know how to read has matched by the
        second turn, the wording is not what we were built for — escalate the strategy."""
        return self.turn >= 2 and self.template_hits == 0

    def add(self, constraint: Constraint) -> None:
        # Preserve the original deterministic contract: only identical surface text is a duplicate.
        # A verified canonical LLM result is the sole exception; it may upgrade an equivalent
        # ontology row so the same fact is not counted twice under two phrasings.
        duplicate = next(
            (
                c
                for c in self.constraints
                if c.alive
                and c.polarity == constraint.polarity
                and (
                    c.text == constraint.text
                    or (
                        constraint.tier == "llm-canonical"
                        and c.attribute == constraint.attribute
                        and c.value == constraint.value
                    )
                )
            ),
            None,
        )
        if duplicate is not None:
            # Canonicalisation may arrive after ontology extracted the same semantic value. Upgrade
            # the existing row so exact matching gains the verified label without double-counting.
            if constraint.tier == "llm-canonical" and duplicate.tier not in {"template", "llm-canonical"}:
                duplicate.source_text = constraint.source_text or duplicate.text
                duplicate.text = constraint.text
                duplicate.tier = constraint.tier
                duplicate.confidence = max(duplicate.confidence, constraint.confidence)
            return
        self.constraints.append(constraint)
        self.resolve_ambiguities(constraint.attribute, constraint.value)
        self.disclosed.add(constraint.text)
        destination = self.exclusions if constraint.polarity == "avoid" else self.slots
        destination.setdefault(constraint.attribute, []).append(constraint.value)
        self.slot_age[constraint.attribute] = 0

    def rebuild_slots(self) -> None:
        """Derive active slots after a transactional remove/replace operation."""
        self.slots = {}
        self.exclusions = {}
        for constraint in self.live():
            destination = self.exclusions if constraint.polarity == "avoid" else self.slots
            values = destination.setdefault(constraint.attribute, [])
            if constraint.value not in values:
                values.append(constraint.value)

    def retire(self, constraint: Constraint, *, turn: int, demote: bool = False) -> None:
        if demote:
            constraint.demoted = True
        else:
            constraint.alive = False
        constraint.superseded_turn = turn
        self.rebuild_slots()

    def live(self) -> list[Constraint]:
        return [c for c in self.constraints if c.alive]

    def add_ambiguity(self, ambiguity: AmbiguousConstraint) -> None:
        """Keep uncertainty separate from confirmed slots and exact-match evidence."""
        if not ambiguity.alternatives:
            return
        key = (
            ambiguity.evidence.lower(),
            tuple((a.attribute, a.value) for a in ambiguity.alternatives),
        )
        for existing in self.ambiguities:
            existing_key = (
                existing.evidence.lower(),
                tuple((a.attribute, a.value) for a in existing.alternatives),
            )
            if existing.alive and existing_key == key:
                return
        self.ambiguities.append(ambiguity)

    def live_ambiguities(self) -> list[AmbiguousConstraint]:
        return [item for item in self.ambiguities if item.alive]

    def resolve_ambiguities(self, attribute: str, value: str | None = None) -> int:
        """Retire uncertainty once a later turn confirms or cancels the relevant slot."""
        changed = 0
        for ambiguity in self.live_ambiguities():
            if any(
                option.attribute == attribute and (value is None or option.value == value)
                for option in ambiguity.alternatives
            ):
                ambiguity.alive = False
                changed += 1
        return changed
