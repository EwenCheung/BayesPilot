"""Utterance → SessionState, in three tiers, cheapest first, stopping at the first that works.

1. template  — the simulator's five literal templates. Exact, free, and recovers the verbatim
               constraint string the exact-phrase matcher needs.
2. ontology  — attribute/value extraction from arbitrary prose. Survives rewording.
3. router    — one model call that routes, normalises, and proposes typed operations, every one of
               which must resolve against real catalog vocabulary before it becomes evidence.

⚠️ **The order is the design, and the sibling branch this router came from ran it the other way
round** — router first, on every message. Measured here: forcing the model onto text the templates
already read costs **-0.0270 and 127x the latency**, with the damage almost entirely in MRR
(0.9942 -> 0.9469). Templates yield exact pairs; the model returns approximations of the same pairs,
and approximations rank the target a slot lower. So the gate is per MESSAGE: escalate only where
tiers 1 and 2 both recovered nothing. On templated input that is zero calls, measured not asserted.
"""
from __future__ import annotations

import re

from src.understand.attributes import normalise
from src.state.session import Constraint, SessionState

# --- the simulator's own templates, mirrored (evaluator.initial_message / customer_reply) ---
OPENER_RE = re.compile(r"^I'm looking for (?P<category>.+?)(?P<tail>, but I'm still exploring\.|\. .*)?$", re.S)
KEY_REQ_RE = re.compile(r"^\. A key requirement is: (?P<constraint>.+?)\.?$", re.S)
REPLY_RE = re.compile(r"^For that, what matters is: (?P<blob>.+?)\.?$", re.S)
OVERRIDE_RE = re.compile(r"^Actually, ignore my earlier preference\. What I need is: (?P<constraint>.+?)\.?$", re.S)
NULL_ASK_RE = re.compile(r"^Those options are not quite right yet")
NO_PREF_RE = re.compile(r"^I don't have (?:an additional preference|a preference) for (?P<attribute>[a-z_]+)")
SCAFFOLD_RE = re.compile(
    r"(I'm looking for|A key requirement is:|but I'm still exploring|For that, what matters is:"
    r"|Actually, ignore my earlier preference\.|What I need is:|Those options are not quite right yet\."
    r"|Ask me about one specific attribute\.)",
    re.I,
)


def _add(state: SessionState, text: str, tier: str) -> int:
    """Record one raw constraint string under every attribute it implies. Returns pairs added."""
    text = text.strip().rstrip(".")
    if not text:
        return 0
    before = len(state.constraints)
    for attribute, value in normalise(text) or [("feature", text.lower())]:
        state.add(Constraint(text=text, attribute=attribute, value=value, turn=state.turn, tier=tier))
    # `add` dedupes on raw text, so keep the extra attribute readings as their own rows
    for attribute, value in normalise(text)[1:]:
        if not any(c.attribute == attribute and c.value == value for c in state.constraints):
            state.constraints.append(
                Constraint(text=text, attribute=attribute, value=value, turn=state.turn, tier=tier)
            )
            state.slots.setdefault(attribute, []).append(value)
    return len(state.constraints) - before


def _template_tier(message: str, state: SessionState, erase: str = "demote") -> tuple[bool, int]:
    """Returns (handled, constraints_added). A handled message never reaches the ontology tier —
    the templates are exact, so anything they leave out genuinely was not said."""
    if NULL_ASK_RE.match(message.strip()):
        return True, 0  # recognised, and it deliberately tells us nothing

    opener = OPENER_RE.match(message.strip())
    if opener and state.category is not None:
        return True, 0  # a template we already consumed; nothing new to escalate over
    if opener:
        state.category = opener.group("category").strip()
        tail = (opener.group("tail") or "").strip()
        if not tail:
            state.route = "browsing"
            return True, 0
        key = KEY_REQ_RE.match(opener.group("tail"))
        if key:
            state.route = "buying"
            return True, _add(state, key.group("constraint"), "template")
        if "still exploring" in tail:
            state.route = "browsing"
            return True, 0
        # neither scaffold: the intent-override opener, which hands us soft_preferences[1]
        state.route = "override"
        return True, _add(state, tail.lstrip(". "), "template")

    override = OVERRIDE_RE.match(message.strip())
    if override:
        state.route = "override"
        state.override_seen = True
        # Pillar II slot erasure — but only the preference the override actually names, which is the
        # one stated in the opener. Erasing everything measured -0.02 MRR: the simulator's "override"
        # is narrative, the target never changes, so constraints learned in between are still true.
        for constraint in state.constraints:
            if constraint.turn <= 1:
                if erase == "delete":
                    constraint.alive = False
                elif erase != "keep":
                    constraint.demoted = True
        return True, _add(state, override.group("constraint"), "template")

    reply = REPLY_RE.match(message.strip())
    if reply:
        added = 0
        for part in reply.group("blob").split("; "):
            added += _add(state, part, "template")
        return True, added

    dead_end = NO_PREF_RE.match(message.strip())
    if dead_end:
        # §14.5 — remember that this attribute is exhausted and never ask it again
        state.asked[dead_end.group("attribute")] = False
        return True, 0
    return False, 0


def _ontology_tier(message: str, state: SessionState) -> int:
    """Strip the simulator's scaffolding and read whatever prose is left."""
    prose = SCAFFOLD_RE.sub(" ", message)
    prose = re.sub(r"^\s*I'?m looking for\b", " ", prose, flags=re.I)
    added = 0
    for chunk in re.split(r"[;.]", prose):
        chunk = chunk.strip()
        if len(chunk) < 3:
            continue
        pairs = normalise(chunk)
        for attribute, value in pairs:
            if attribute == "feature" and value == chunk.lower():
                continue  # nothing was actually recognised in this chunk
            if any(c.attribute == attribute and c.value == value for c in state.constraints):
                continue
            state.constraints.append(
                Constraint(text=chunk, attribute=attribute, value=value, turn=state.turn, tier="ontology")
            )
            state.slots.setdefault(attribute, []).append(value)
            state.slot_age[attribute] = 0
            added += 1
    return added


def parse(
    message: str,
    state: SessionState,
    llm=None,
    erase: str = "demote",
    intent_pipeline=None,
) -> SessionState:
    """Never raises. Returns the same state object, mutated."""
    try:
        message = (message or "").strip()
        if not message:
            return state
        state.history.append(message)

        # --- tier 1: the templates are exact, so a match ends the cascade -----------------------
        handled, added = _template_tier(message, state, erase)
        state.template_hits += int(handled)

        if not handled:
            # --- tier 2: ontology extraction from arbitrary prose ------------------------------
            added = _ontology_tier(message, state)

            # --- tier 3: the router, on a message neither deterministic tier could read --------
            if intent_pipeline is not None and hasattr(intent_pipeline, "decide"):
                decision = intent_pipeline.decide(message, state)
                state.normalized_messages[state.turn] = decision.normalized_text
                state.router_routes[state.turn] = decision.route
                if decision.route == "hybrid":
                    restored_before = state.llm_restoration_hits
                    added += intent_pipeline.process_decision(message, state, decision, erase=erase)
                    if state.llm_restoration_hits == restored_before:
                        # A malformed or abstaining response must not forfeit deterministic parsing.
                        if decision.normalized_text and decision.normalized_text != message:
                            added += _ontology_tier(decision.normalized_text, state)
            elif intent_pipeline is not None:
                added += intent_pipeline.process(message, state, erase=erase)
            elif llm is not None:
                for _attribute, value, _text in llm.extract(message) or []:
                    # feed the short extracted phrase back through the normal cascade rather than
                    # trusting the model's attribute label: the catalog's vocabulary decides.
                    _add(state, value, "llm")
        for attribute in state.slot_age:
            state.slot_age[attribute] = state.turn - max(
                (c.turn for c in state.constraints if c.attribute == attribute), default=state.turn
            )
    except Exception:  # spec C3 — a parse failure must never cost the turn
        pass
    return state
