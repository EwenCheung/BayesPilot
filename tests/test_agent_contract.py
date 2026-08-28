"""Spec C1–C5 — the contract the evaluator actually enforces, tested on the real catalog."""
import inspect
from pathlib import Path

import pytest

from src.r1.agent import Agent

CATALOG = Path(__file__).parent.parent / "techjam-conversational-search-main" / "data" / "catalog.jsonl"
PROFILE = {"preference_tags": ["fit", "comfort"], "purchase_frequency": "3-4 prior purchases"}


@pytest.fixture(scope="module")
def agent():
    return Agent(CATALOG)


def test_init_signature_is_positional_and_defaulted():
    """C1 — undocumented, and the evaluator calls it positionally (IMPORTANT.md §13.1.2)."""
    parameters = list(inspect.signature(Agent.__init__).parameters.values())
    assert parameters[1].name == "catalog_path"
    assert parameters[1].default == "data/catalog.jsonl"


def test_respond_shape_is_always_valid(agent):
    agent.reset("s1", PROFILE)
    response = agent.respond("s1", "I'm looking for Shirts T-Shirts. A key requirement is: Material: cotton.", 1, 10)
    assert isinstance(response["message"], str) and response["message"]
    assert response["ask_attribute"] in {
        "category", "material", "color", "size", "style", "brand", "budget", "feature", "use_case", "other"
    }
    assert isinstance(response["recommendations"], list)
    assert all("parent_asin" in item for item in response["recommendations"])
    assert response["usage"]["prompt_tokens"] >= 0


def test_respond_never_raises_on_garbage(agent):
    agent.reset("s2", PROFILE)
    for turn, message in enumerate(["", "?????", "\x00\x01", "a" * 5000], start=1):
        response = agent.respond("s2", message, turn, 10)
        assert isinstance(response, dict)


def test_unknown_session_still_answers(agent):
    """The evaluator always calls reset first, but a forfeited turn is never worth the risk."""
    response = agent.respond("never-reset", "I'm looking for Dresses Casual, but I'm still exploring.", 1, 10)
    assert isinstance(response["recommendations"], list)


def test_reset_clears_session_state_but_keeps_the_index(agent):
    """C5 — one instance serves 200 sessions; leaking slots between them would be silent poison."""
    agent.reset("s3", PROFILE)
    agent.respond("s3", "I'm looking for Shirts T-Shirts. A key requirement is: Material: cotton.", 1, 10)
    assert agent.sessions["s3"].live()
    agent.reset("s3", PROFILE)
    assert not agent.sessions["s3"].live()
    assert agent.sessions["s3"].category is None
    assert len(agent.index.popularity) == 50000


def test_override_sessions_stay_silent_until_conversion_is_legal(agent):
    """Spec 3.9 — turns 1–2 are discarded in override sessions, so they buy information instead."""
    agent.reset("s4", PROFILE)
    first = agent.respond("s4", "I'm looking for Watches Wrist Watches. Band width: 20 millimeters", 1, 10)
    assert first["recommendations"] == []
    assert first["ask_attribute"] is not None
    third = agent.respond("s4", "Actually, ignore my earlier preference. What I need is: Material: alloy.", 3, 10)
    assert third["recommendations"], "must convert once the override has landed"


def test_patience_then_deadline(agent):
    """Spec 3.9 — an ambiguous turn 1 stays silent (worth +0.042, IMPORTANT.md §12.1),
    but the deadline forces a list by turn 3 no matter what."""
    agent.reset("s5", PROFILE)
    opener = "I'm looking for Shirts T-Shirts. A key requirement is: 100% Cotton."
    first = agent.respond("s5", opener, 1, 10)
    assert first["recommendations"] == [], "one common constraint is not convergence"
    third = agent.respond("s5", "For that, what matters is: color: blue.", 3, 10)
    assert third["recommendations"], "the deadline must fire"
    assert all(item["parent_asin"] in agent.index.popularity for item in third["recommendations"])


def test_filter_shrinks_as_constraints_arrive(agent):
    """Spec 3.6 — the defining behaviour of R1: S gets smaller, and never empties."""
    from src.r1.filter import survivors

    agent.reset("s6", PROFILE)
    state = agent.sessions["s6"]
    state.turn = 1
    agent.respond("s6", "I'm looking for Shirts T-Shirts, but I'm still exploring.", 1, 10)
    sizes = [len(survivors(agent.index, state, agent.flags)[0])]
    for turn, message in enumerate(["For that, what matters is: 100% Cotton; color: blue.",
                                    "For that, what matters is: Machine Wash."], start=2):
        agent.respond("s6", message, turn, 10)
        sizes.append(len(survivors(agent.index, state, agent.flags)[0]))
    assert sizes[0] > sizes[-1] > 0, sizes


def test_paraphrase_mode_is_detected_at_runtime(agent):
    """Pillar III — the agent notices when its own parsers stopped working and escalates."""
    from src.common.contracts import SessionState
    from src.common.parse import parse

    clean = SessionState()
    for turn, message in enumerate(["I'm looking for Dresses Casual, but I'm still exploring.",
                                    "For that, what matters is: 100% Cotton."], start=1):
        clean.turn = turn
        parse(message, clean)
    assert not clean.paraphrased()

    reworded = SessionState()
    for turn, message in enumerate(["just browsing Dresses Casual at the moment",
                                    "mainly pure cotton"], start=1):
        reworded.turn = turn
        parse(reworded_message := message, reworded)
    assert reworded.paraphrased()


def test_usage_is_reported_as_per_turn_deltas(agent):
    """The evaluator SUMS `usage` across turns, so running totals over-count quadratically.
    Token usage is a disclosed submission figure — it has to be right."""
    class CountingLLM:
        prompt_tokens = 0
        completion_tokens = 0

        def extract(self, message):
            CountingLLM.prompt_tokens += 100
            CountingLLM.completion_tokens += 10
            return []

        def rerank(self, query, candidates, labels=None):
            return None  # the adaptive gate fires this once the session looks paraphrased

    agent.reset("s7", PROFILE)
    original, agent.llm = agent.llm, CountingLLM()
    agent.flags.llm_extract = True
    try:
        totals = [agent.respond("s7", f"some reworded request number {turn}", turn, 10)["usage"]
                  for turn in range(1, 4)]
    finally:
        agent.llm = original
        agent.flags.llm_extract = False
    assert [u["prompt_tokens"] for u in totals] == [100, 100, 100], totals
    assert sum(u["prompt_tokens"] for u in totals) == CountingLLM.prompt_tokens
