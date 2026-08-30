"""Recover category and route from a free-form opener — the two things the templates gave us free.

📊 Measured on `data/freeform_v1/validation.jsonl` (400 sessions), R4 as shipped:

| | |
|---|---|
| `state.category` parsed from the opener | **0.0%** |
| >=1 constraint parsed | 91.8% |
| route detected | **100% "browsing"** — i.e. the dataclass default, never a decision |

`OPENER_RE` needs the literal `"I'm looking for {category}"`, and the corpus never says it. Constraint
extraction survives because the ontology tier reads free text, but category and route come only from
the template, so both silently collapse. Route collapsing to its default is the more damaging of the
two: R4's `exclude_shipped` soundness guard treats an unparsed opener as "assume nothing" (D9), so
every early turn stays unproven and the mechanism runs at half strength.

Both are recoverable **without a model**. The category name is usually present verbatim in the
opener — "yo, need & utility shoes", "browsing shoes oxfords no fixed preferences yet" — and the
catalog gives us the closed vocabulary of 1,115 coarse categories to match it against. The route is
carried by cue words the styles preserve.
"""
from __future__ import annotations

import re

from src.common.attributes import tokens

# Cues survive restyling because they carry the speech act, not the content.
BROWSE_CUES = ("no fixed preference", "still exploring", "browsing", "just looking", "not sure",
               "nothing fixed", "open on specifics", "having a look", "no strong preference")
BUY_CUES = ("must have", "biggest thing", "priority is", "important part", "important bit",
            "key requirement", "really need", "rlly need", "needs to be", "matters most",
            "has to be", "must be", "keep ", "want ")
OVERRIDE_CUES = ("actually", "scratch that", "change of plan", "instead", "make it", "forget what")


def route_of(message: str, default: str = "browsing") -> str:
    """buying | browsing | intent_override, from cue words alone.

    ⚠️ Order matters. An override opener also contains a requirement, and a browsing opener can
    contain "want" — so the most specific speech act is tested first and the vaguest last.
    """
    low = (message or "").lower()
    if any(cue in low for cue in OVERRIDE_CUES):
        return "override"
    if any(cue in low for cue in BROWSE_CUES):
        return "browsing"
    if any(cue in low for cue in BUY_CUES):
        return "buying"
    return default


class CategoryMatcher:
    """Closed-vocabulary match of a free-form opener against the catalog's coarse categories.

    Deterministic, no network. Built once from the same category table the belief already holds, so
    it adds no index and no memory beyond an inverted token map.
    """

    def __init__(self, names) -> None:
        self.names = list(names)
        self._toks = [frozenset(tokens(n)) for n in self.names]
        self._inv: dict[str, list[int]] = {}
        for i, ts in enumerate(self._toks):
            for t in ts:
                self._inv.setdefault(t, []).append(i)

    def best(self, message: str, floor: float = 0.34) -> str | None:
        """The category whose name best overlaps the opener, or None when nothing clears `floor`.

        ⚠️ Returns None rather than a guess. `state.category` is read as *positive evidence that the
        opener was understood* (R4 D9) — a wrong value there is worse than no value, because it
        unlocks the exclusion guard on a session we did not actually parse.
        """
        want = frozenset(tokens(message or ""))
        if not want:
            return None
        hits: dict[int, int] = {}
        for t in want:
            for i in self._inv.get(t, ()):
                hits[i] = hits.get(i, 0) + 1
        best_i, best_score = None, 0.0
        for i in hits:
            ts = self._toks[i]
            if not ts:
                continue
            # coverage of the CATEGORY's tokens, not of the message: an opener carries constraint
            # words too, and Jaccard against the whole message punishes the long ones unfairly
            score = len(want & ts) / len(ts)
            if score > best_score or (score == best_score and best_i is not None and len(ts) > len(self._toks[best_i])):
                best_i, best_score = i, score
        return self.names[best_i] if best_i is not None and best_score >= floor else None


# --- the escalation predicate (R5 D18) -----------------------------------------------------------
# `SessionState.paraphrased()` is `turn >= 2 and template_hits == 0` — a SESSION-level detector,
# evaluated at the start of turn t against hits accumulated through turn t-1. On a corpus whose
# opener is restyled but whose replies are templated, that fires on turn 2 and hands the model a
# perfectly parseable reply, while the opener that needed it was blocked by `turn >= 2`. Measured:
# the gate opened in 90.5% of free-form sessions, always on turn 2, always on a templated message.
#
# This predicate asks the only question that matters: **can the deterministic path read THIS
# message?** Per turn, no session history.

def reads_deterministically(message: str, turn: int) -> bool:
    """Can the deterministic path recover everything THIS message carries?

    ⚠️ "Recovered something" is not the same as "read it". A free-form opener like
    *"yo, need & utility shoes; biggest thing is leather"* yields `material=leather` from the ontology
    tier, so a naive predicate calls it readable — while the **category**, which only the opener
    template can recover and which no later turn ever repeats, is silently lost. That is precisely
    the message escalation exists for, so the test is per message TYPE:

    * **turn 1** carries the category. Readable only if `OPENER_RE` matches.
    * **later turns** carry constraints. Readable if a template matches or the ontology finds a pair.

    ⚠️ The two "recognised but empty" templates count as readable. `NULL_ASK_RE` and `NO_PREF_RE` are
    the simulator saying it has nothing to add; escalating there spends a call to rediscover that.
    """
    from src.common.attributes import normalise
    from src.common.parse import NO_PREF_RE, NULL_ASK_RE, OPENER_RE, OVERRIDE_RE, REPLY_RE

    text = (message or "").strip()
    if not text:
        return True                       # nothing to escalate over
    if turn <= 1:
        return bool(OPENER_RE.match(text))
    for pattern in (REPLY_RE, OVERRIDE_RE, NULL_ASK_RE, NO_PREF_RE, OPENER_RE):
        if pattern.match(text):
            return True
    return bool(normalise(text))
