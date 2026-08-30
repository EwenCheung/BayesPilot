from __future__ import annotations

from pathlib import Path

from src.r3.agent import Agent


CATALOG = Path(__file__).parent.parent / "assets" / "catalog.jsonl"


class AttributeSelector:
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def select_attribute(self, profile, state):
        self.prompt_tokens += 11
        self.completion_tokens += 3
        return "size"

    def totals(self):
        return self.prompt_tokens, self.completion_tokens


def test_attribute_selector_changes_only_the_question_policy(monkeypatch) -> None:
    monkeypatch.setenv("R3_OFFLINE", "1")
    baseline = Agent(CATALOG)
    monkeypatch.delenv("R3_OFFLINE")
    with_selector = Agent(CATALOG)
    with_selector.flags.llm_attribute = True
    with_selector.llm = AttributeSelector()

    profile = {"preference_tags": ["fit"]}
    message = "I'm looking for Belts, but I'm still exploring."
    baseline.reset("baseline", profile)
    with_selector.reset("selector", profile)
    plain = baseline.respond("baseline", message, 1, 10)
    selected = with_selector.respond("selector", message, 1, 10)

    assert plain["ask_attribute"] == "other"
    assert selected["ask_attribute"] == "size"
    assert selected["recommendations"] == plain["recommendations"]
    assert selected["message"] == "What size, dimensions, or fit do you need?"
    assert selected["usage"] == {"prompt_tokens": 11, "completion_tokens": 3}


def test_critical_question_is_specific_and_contract_legal(monkeypatch) -> None:
    monkeypatch.setenv("R3_OFFLINE", "1")
    agent = Agent(CATALOG)
    agent.flags.critical_questions = True
    agent.reset("critical", {})
    response = agent.respond(
        "critical", "I'm looking for Belts, but I'm still exploring.", 1, 10
    )
    assert response["ask_attribute"] in {
        "material", "size", "color", "use_case", "style", "feature"
    }
    assert response["ask_attribute"] != "other"


def test_customer_answers_update_slots_and_override_demotes_old_intent(monkeypatch) -> None:
    monkeypatch.setenv("R3_OFFLINE", "1")
    agent = Agent(CATALOG)
    agent.reset("state", {})
    agent.respond(
        "state", "I'm looking for Belts. A key requirement is: leather.", 1, 10
    )
    agent.respond(
        "state", "For that, what matters is: color: black.", 2, 10
    )
    state = agent.sessions["state"]
    assert state.slots.get("material")
    assert state.slots.get("color")

    agent.respond(
        "state",
        "Actually, ignore my earlier preference. What I need is: material: nylon.",
        3,
        10,
    )
    assert any(item.demoted for item in state.constraints if item.turn == 1)
    assert any(item.value == "nylon" for item in state.constraints if item.turn == 3)
