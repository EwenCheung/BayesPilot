"""SessionState and the shared parser.

All three roads call `parse()` so they see identical input; only what they do with it differs.

Parsing is layered on purpose. A template fast path handles the simulator's exact sentences, and a
carrier-stripping fallback handles anything reworded. The fallback is the part that matters for the
private set — if the organizer paraphrases, the templates stop firing and this is what keeps constraints
flowing into the slots (docs/r2-exploration/00-r2-spec.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .simulator import classify_constraint

# Template fast path — the simulator's exact sentences.
CATEGORY_RE = re.compile(
    r"looking for (?P<cat>.+?)"
    r"(?:,?\s*but I'm still exploring\.?"
    r"|\.\s*A key requirement is:\s*(?P<hard>.*?)\.?$"
    r"|\.\s*(?P<soft>.*)$"
    r"|$)",
    re.I,
)
REPLY_RE = re.compile(r"^For that, what matters is:\s*(?P<body>.*?)\.?$", re.I)
OVERRIDE_RE = re.compile(
    r"ignore my earlier preference\.?\s*What I need is:\s*(?P<body>.*?)\.?$", re.I
)
NO_PREF_RE = re.compile(r"(?:have|has) (?:an additional |a |any )?preference for (?P<attr>\w+)", re.I)

# Discourse filler stripped from the head/tail of a paraphrased utterance. These carry no product
# information, and leaving them attached would corrupt an otherwise exact spec-phrase match.
FILLERS = frozenset("""
hi hey hello ok okay so well yeah yes um uh honestly actually really just maybe perhaps
please thanks thank you sure right now for
""".split())

# Carrier phrases stripped by the paraphrase-tolerant fallback. Ordered longest-first at match time.
CARRIERS = (
    "for that what matters is", "what matters is", "a key requirement is",
    "what i need is", "ignore my earlier preference", "actually ignore my earlier preference",
    "i'm looking for", "im looking for", "i am looking for", "looking for",
    "but i'm still exploring", "but im still exploring", "still exploring",
    "please use your judgment", "ask me about one specific attribute",
    "those options are not quite right yet", "i need", "i want", "it has to be",
    "it should be", "needs to be", "must be", "show me", "something",
)
OVERRIDE_CUES = ("ignore my earlier", "instead of", "actually", "forget that", "scratch that",
                 "changed my mind", "rather than")
NO_PREF_CUES = ("don't have a preference", "dont have a preference", "no preference",
                "don't have an additional", "dont have an additional", "use your judgment")


@dataclass
class Constraint:
    """One thing the customer told us, with provenance so override can erase the right one."""
    value: str
    turn: int
    source: str  # "initial_hard" | "initial_soft" | "reply" | "override"

    @property
    def attribute(self) -> str:
        return classify_constraint(self.value)


@dataclass
class SessionState:
    turn: int = 0
    category: str | None = None          # as stated by the customer, before catalog resolution
    resolved_category: str | None = None  # after CatalogIndex.resolve_category
    constraints: list[Constraint] = field(default_factory=list)
    disclosed: set[str] = field(default_factory=set)
    history: list[str] = field(default_factory=list)
    profile: dict = field(default_factory=dict)
    long_term: dict = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)
    barren: set[str] = field(default_factory=set)   # attributes that yielded nothing
    shown: list[str] = field(default_factory=list)  # asins already recommended
    override_seen: bool = False

    @property
    def slots(self) -> dict[str, list[str]]:
        """attribute -> confirmed values (Pillar II: incremental slots)."""
        out: dict[str, list[str]] = {}
        for c in self.constraints:
            out.setdefault(c.attribute, []).append(c.value)
        return out

    @property
    def slot_age(self) -> dict[str, int]:
        """Turns since each slot was last confirmed (PROBLEM.md §4.3, slot decay over time)."""
        newest: dict[str, int] = {}
        for c in self.constraints:
            newest[c.attribute] = max(newest.get(c.attribute, 0), c.turn)
        return {attr: self.turn - t for attr, t in newest.items()}

    def values(self) -> list[str]:
        return [c.value for c in self.constraints]

    def weight_of(self, c: Constraint, decay: float) -> float:
        """Slot decay: a constraint confirmed long ago counts for less than a fresh one.

        decay=0.0 disables it (every constraint weighs 1.0), which is the ablation.
        """
        age = max(0, self.turn - c.turn)
        return 1.0 / (1.0 + decay * age)


def _strip_carriers(text: str) -> str:
    out = text.strip()
    lowered = out.lower()
    for carrier in sorted(CARRIERS, key=len, reverse=True):
        idx = lowered.find(carrier)
        if idx != -1:
            out = (out[:idx] + " " + out[idx + len(carrier):]).strip()
            lowered = out.lower()
    out = re.sub(r"\s+", " ", out).strip(" .,;:-—")
    words = out.split(" ")
    while words and words[0].lower().strip(",.!—-") in FILLERS:
        words.pop(0)
    while words and words[-1].lower().strip(",.!—-") in FILLERS:
        words.pop()
    return " ".join(words).strip(" .,;:-—")


def _split_values(body: str) -> list[str]:
    """The simulator joins two constraints with '; '. Keep both the parts and the whole.

    The whole blob is kept because a single constraint can legitimately contain a semicolon, and the
    spec-phrase route scores against exact catalog strings — a false split would lose an exact match.
    """
    body = body.strip().rstrip(".")
    if not body:
        return []
    parts = [p.strip().rstrip(".") for p in body.split(";")]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else [body]


def parse(message: str, state: SessionState, turn: int) -> SessionState:
    """Fold one customer utterance into the state. Mutates and returns `state`."""
    state.turn = turn
    state.history.append(message)
    text = message.strip()
    lowered = text.lower()

    # "I don't have a preference for X" — boundary sessions and exhausted attributes. Record that the
    # attribute is barren so we never spend another turn on it (Pillar III: refine our own guidance logic).
    if any(cue in lowered for cue in NO_PREF_CUES):
        match = NO_PREF_RE.search(text)
        if match:
            state.barren.add(match.group("attr").lower())
        return state

    if "ask me about one specific attribute" in lowered:
        return state

    # Intent override — erase before writing (Pillar II: slot erasure, not contradiction stacking).
    override = OVERRIDE_RE.search(text)
    if override or (any(cue in lowered for cue in OVERRIDE_CUES) and state.constraints):
        body = override.group("body") if override else _strip_carriers(text)
        state.override_seen = True
        # The superseded preference is whatever the opening message trailed with; the evaluator builds
        # override.old_value from soft_preferences[-1] and puts it in the turn-1 sentence.
        state.constraints = [c for c in state.constraints if c.source != "initial_soft"]
        for value in _split_values(body):
            if value not in state.disclosed:
                state.constraints.append(Constraint(value, turn, "override"))
                state.disclosed.add(value)
        return state

    # Answer to a question.
    reply = REPLY_RE.match(text)
    if reply:
        for value in _split_values(reply.group("body")):
            if value not in state.disclosed:
                state.constraints.append(Constraint(value, turn, "reply"))
                state.disclosed.add(value)
        return state

    # Opening message: category, plus possibly one constraint.
    opening = CATEGORY_RE.search(text)
    if opening and state.category is None:
        state.category = (opening.group("cat") or "").strip().rstrip(".,")
        hard, soft = opening.group("hard"), opening.group("soft")
        if hard:
            for value in _split_values(hard):
                state.constraints.append(Constraint(value, turn, "initial_hard"))
                state.disclosed.add(value)
        elif soft:
            # Override sessions open with soft_preferences[-1] here, unmarked as disclosed by the
            # evaluator. It is real information now and erasable later.
            for value in _split_values(soft):
                state.constraints.append(Constraint(value, turn, "initial_soft"))
        return state

    # Nothing matched a template: paraphrase, or an unfamiliar sentence. Take what is left after the
    # carrier phrases are removed and treat it as a constraint.
    residue = _strip_carriers(text)
    if residue and residue not in state.disclosed:
        source = "initial_soft" if state.category is None else "reply"
        if state.category is None:
            state.category = residue
        else:
            for value in _split_values(residue):
                state.constraints.append(Constraint(value, turn, source))
                state.disclosed.add(value)
    return state
