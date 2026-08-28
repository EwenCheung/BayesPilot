"""Spec 3.4 — every simulator template parses exactly; paraphrases degrade gracefully."""
from src.common.contracts import SessionState
from src.common.parse import parse

BUY = "I'm looking for Shirts T-Shirts. A key requirement is: Material: cotton."
BROWSE = "I'm looking for Shoes Fashion Sneakers, but I'm still exploring."
OVERRIDE_OPEN = "I'm looking for Watches Wrist Watches. Band width: 20 millimeters"
REPLY = "For that, what matters is: color: black; Closure type: Buckle."
OVERRIDE = "Actually, ignore my earlier preference. What I need is: Material: alloy."
NO_PREF = "I don't have an additional preference for material."
BOUNDARY = "I don't have a preference for other; please use your judgment."
NULL_ASK = "Those options are not quite right yet. Ask me about one specific attribute."


def parsed(*messages) -> SessionState:
    state = SessionState()
    for turn, message in enumerate(messages, start=1):
        state.turn = turn
        parse(message, state)
    return state


def test_buying_turn_one_gives_category_route_and_the_verbatim_constraint():
    state = parsed(BUY)
    assert state.category == "Shirts T-Shirts"
    assert state.route == "buying"
    assert "Material: cotton" in state.disclosed


def test_browsing_turn_one_gives_category_only():
    state = parsed(BROWSE)
    assert state.category == "Shoes Fashion Sneakers"
    assert state.route == "browsing"
    assert not state.live()


def test_override_scenario_is_detectable_on_turn_one():
    """Spec 3.4 / Pillar I — the opener carries soft_preferences[1] and no scaffold phrase."""
    state = parsed(OVERRIDE_OPEN)
    assert state.category == "Watches Wrist Watches"
    assert state.route == "override"
    assert "Band width: 20 millimeters" in state.disclosed


def test_reply_splits_both_constraints_verbatim():
    state = parsed(BROWSE, REPLY)
    assert {"color: black", "Closure type: Buckle"} <= state.disclosed
    assert {c.attribute for c in state.live()} >= {"color", "style"}


def test_override_erases_the_old_slot_and_adds_the_new_one():
    """Pillar II — slot erasure, not just accumulation."""
    state = parsed(OVERRIDE_OPEN, OVERRIDE)
    assert "Material: alloy" in state.disclosed
    retired = [c for c in state.constraints if c.demoted]
    assert [c.text for c in retired] == ["Band width: 20 millimeters"]
    fresh = next(c for c in state.constraints if c.text == "Material: alloy")
    assert retired[0].weight(state.turn) < fresh.weight(state.turn)

    from src.common.parse import parse as _parse
    hard = SessionState()
    hard.turn = 1
    _parse(OVERRIDE_OPEN, hard, erase="delete")
    hard.turn = 2
    _parse(OVERRIDE, hard, erase="delete")
    assert [c.text for c in hard.constraints if not c.alive] == ["Band width: 20 millimeters"]


def test_no_preference_replies_record_a_dead_end_and_add_nothing():
    """§14.5 — the agent must stop re-asking an attribute that yielded nothing."""
    state = parsed(BROWSE, NO_PREF, BOUNDARY, NULL_ASK)
    assert state.asked.get("material") is False
    assert not state.live()


def test_slot_decay_downweights_stale_constraints():
    state = parsed(BUY, REPLY)
    state.turn = 5
    old = next(c for c in state.live() if c.text == "Material: cotton")
    fresh = next(c for c in state.live() if c.text == "color: black")
    assert old.weight(state.turn) < fresh.weight(state.turn)


def test_paraphrased_message_still_yields_slots():
    """The whole paraphrase bet: no template, no verbatim string, but the ontology still fires."""
    state = parsed("hey, I want some sneakers - ideally made of leather, in black")
    attributes = {c.attribute for c in state.live()}
    assert {"material", "color"} <= attributes
    assert all(c.tier == "ontology" for c in state.live())


def test_parse_never_raises():
    for message in ["", "?!?", "For that, what matters is: .", "I'm looking for ."]:
        parse(message, SessionState())


class StubLLM:
    """Records calls so we can prove the escalation policy, not just the parsing."""

    def __init__(self, pairs=()):
        self.pairs = list(pairs)
        self.calls = 0

    def extract(self, message):
        self.calls += 1
        return self.pairs


def test_llm_tier_never_fires_on_clean_template_text():
    """The escalation contract: on the clean set the LLM costs exactly nothing."""
    llm = StubLLM([("material", "leather", "x")])
    state = SessionState()
    for turn, message in enumerate([BUY, REPLY, OVERRIDE, NO_PREF, BROWSE], start=1):
        state.turn = turn
        parse(message, state, llm=llm)
    assert llm.calls == 0


def test_llm_tier_fires_on_unrecognised_text_and_feeds_the_normal_cascade():
    llm = StubLLM([("feature", "buckle closure", "raw")])
    state = SessionState()
    state.turn = 1
    parse("honestly I just want something with a buckle closure", state, llm=llm)
    assert llm.calls == 1
    constraint = next(c for c in state.live() if c.tier == "llm")
    # the model's own attribute label is not trusted; the catalog's vocabulary decides
    assert constraint.text == "buckle closure"


def test_llm_failure_leaves_the_turn_usable():
    """C8 — an unreachable endpoint degrades to the deterministic result, never to an exception."""
    class DeadLLM:
        def extract(self, message):
            return []

    state = SessionState()
    state.turn = 1
    parse("something in black leather", state, llm=DeadLLM())
    assert {c.attribute for c in state.live()} >= {"material", "color"}
