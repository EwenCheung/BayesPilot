from __future__ import annotations

from src.common.contracts import Constraint, SessionState
from src.common.intent import IntentPipeline, RoutingDecision, validate_operations
from src.common.parse import parse


class StubIndex:
    def __init__(self) -> None:
        self.labels = {
            "material": ["100% Cotton", "leather"],
            "color": ["color: blue"],
            "size": ["XL"],
            "style": ["Dressy"],
            "use_case": ["Winter", "Machine washable", "Hand Wash", "Imported"],
        }

    def exact_canonical(self, attribute: str, value: str):
        key = value.lower().strip()
        aliases = {
            ("material", "cotton"): "100% Cotton",
            ("use_case", "washer safe"): "Machine washable",
            ("use_case", "from abroad"): "Imported",
            ("style", "dressy"): "Dressy",
            ("color", "blue"): "color: blue",
        }
        if (attribute, key) in aliases:
            return aliases[(attribute, key)]
        return next((label for label in self.labels.get(attribute, []) if label.lower() == key), None)

    def canonical_candidates(self, attribute: str, phrase: str, limit: int = 8):
        wanted = set(phrase.lower().split())
        return [
            label for label in self.labels.get(attribute, [])
            if wanted & set(label.lower().split())
        ][:limit]


class StubLLM:
    def __init__(self, operations, decisions=()) -> None:
        self.operations = operations
        self.decisions = list(decisions)
        self.interpret_calls = 0
        self.resolve_calls = 0

    def interpret_operations(self, message, state):
        self.interpret_calls += 1
        return self.operations

    def resolve_canonical(self, attribute, phrase, candidates, *, allow_generate):
        self.resolve_calls += 1
        if self.decisions:
            return self.decisions.pop(0)
        return {"selected": candidates[0] if candidates else None, "generated_query": None}


def operation(op, attribute, value, evidence, **extra):
    return {
        "op": op,
        "attribute": attribute,
        "value": value,
        "evidence": evidence,
        "polarity": extra.get("polarity", "require"),
        "strength": extra.get("strength", "hard"),
        "confidence": extra.get("confidence", 0.95),
        "group": extra.get("group"),
    }


def test_unquoted_or_low_confidence_model_claims_are_rejected():
    message = "I need something in black"
    rows = [
        operation("add", "color", "blue", "blue", confidence=0.99),
        operation("add", "color", "black", "black", confidence=0.2),
    ]
    assert validate_operations(rows, message) == []


def test_low_confidence_alternatives_survive_only_as_a_valid_group():
    message = "Requirement: poly"
    grouped = [
        operation("add", "material", "polyester", "poly", confidence=0.8, group="poly"),
        operation("add", "feature", "polycarbonate", "poly", confidence=0.1, group="poly"),
        operation("add", "feature", "polyurethane", "poly", confidence=0.1, group="poly"),
    ]
    accepted = validate_operations(grouped, message)
    assert len(accepted) == 3
    assert {item.group for item in accepted} == {"poly"}


def test_llm_routes_a_clean_template_to_deterministic_processing_once():
    class ReviewPipeline:
        def __init__(self):
            self.calls = 0

        def decide(self, message, state):
            self.calls += 1
            return RoutingDecision(
                "deterministic", message, "buying", "Shirts", "", ()
            )

        def process_decision(self, message, state, decision, *, erase="demote"):
            raise AssertionError("deterministic route must not apply model operations")

    pipeline = ReviewPipeline()
    state = SessionState(turn=1)
    parse(
        "I'm looking for Shirts. A key requirement is: 100% Cotton.",
        state,
        intent_pipeline=pipeline,
    )
    assert pipeline.calls == 1
    assert state.router_routes[1] == "deterministic"
    assert state.normalized_messages[1].startswith("I'm looking for Shirts")
    assert "100% Cotton" in state.disclosed


def test_deterministic_route_ignores_model_operations_and_trusts_template_parser():
    class RouterLLM(StubLLM):
        def restore_template(self, message, state):
            self.interpret_calls += 1
            return {
                "route": "deterministic",
                "normalized_text": message,
                "kind": "buying",
                "category": "Shirts",
                "operations": [operation("add", "color", "blue", "Cotton")],
            }

    llm = RouterLLM([])
    state = SessionState(turn=1)
    parse(
        "I'm looking for Shirts. A key requirement is: 100% Cotton.",
        state,
        intent_pipeline=IntentPipeline(StubIndex(), llm),
    )
    assert llm.interpret_calls == 1
    assert state.slots == {"material": ["cotton"]}
    assert all(item.attribute != "color" for item in state.constraints)


def test_hybrid_route_reuses_the_same_router_response():
    class HybridIndex(StubIndex):
        def is_trusted_alias(self, attribute, evidence, value):
            return (attribute, evidence.lower(), value.lower()) == (
                "material", "cotten", "cotton"
            )

    class RestoreLLM(StubLLM):
        def restore_template(self, message, state):
            self.interpret_calls += 1
            return {
                "route": "hybrid",
                "normalized_text": "I need shoes made of cotton.",
                "kind": "buying",
                "category": "kicks",
                "operations": [operation("add", "material", "cotton", "cotten")],
            }

    class Categories:
        def resolve_candidates(self, phrase):
            return [("Shoes Fashion Sneakers", 1.0)]

        def resolve_phrase(self, phrase):
            return "Shoes Fashion Sneakers"

    llm = RestoreLLM([])
    state = SessionState(turn=1)
    parse(
        "need kicks made of cotten",
        state,
        intent_pipeline=IntentPipeline(HybridIndex(), llm, Categories()),
    )
    assert llm.interpret_calls == 1
    assert state.router_routes[1] == "hybrid"
    assert state.normalized_messages[1] == "I need shoes made of cotton"
    assert state.slots["material"] == ["cotton"]


def test_paraphrased_opener_is_restored_to_verified_fixed_template():
    class CategoryBelief:
        def resolve_phrase(self, phrase):
            assert phrase == "womens shirts tees"
            return "Shirts T-Shirts"

    class RestoreLLM(StubLLM):
        def restore_template(self, message, state):
            self.interpret_calls += 1
            return {
                "kind": "buying",
                "category": "womens shirts tees",
                "attribute": None,
                "operations": [
                    operation("add", "material", "cotton", "pure Cotton"),
                    operation("add", "color", "blue", "Blue colour"),
                ],
            }

    message = (
        "shopping for womens shirts tees and it really has to be "
        "Blue colour and pure Cotton made of"
    )
    llm = RestoreLLM([])
    state = SessionState(turn=1)
    parse(
        message,
        state,
        intent_pipeline=IntentPipeline(StubIndex(), llm, CategoryBelief()),
    )
    assert state.category == "Shirts T-Shirts"
    assert state.route == "buying"
    assert state.restored_messages[1].startswith(
        "I'm looking for Shirts T-Shirts. A key requirement is:"
    )
    assert state.template_hits == 1


def test_reworded_material_is_upgraded_to_verified_exact_label():
    message = "I need it made entirely of cotton"
    llm = StubLLM(
        [operation("add", "material", "cotton", "made entirely of cotton")],
    )
    state = SessionState(turn=1)
    parse(message, state, intent_pipeline=IntentPipeline(StubIndex(), llm))
    constraint = next(item for item in state.live() if item.attribute == "material")
    assert constraint.text == "100% Cotton"
    assert constraint.source_text == "made entirely of cotton"
    assert constraint.tier == "llm-canonical"


def test_trusted_alias_resolves_without_a_second_llm_call():
    message = "It has to be washer safe"
    llm = StubLLM(
        [operation("add", "use_case", "washer safe", "washer safe")],
    )
    state = SessionState(turn=1)
    IntentPipeline(StubIndex(), llm).process(message, state, erase="delete")
    assert next(iter(state.live())).text == "Machine washable"
    assert llm.resolve_calls == 0


def test_override_removes_blue_and_keeps_winter():
    message = "Actually forget the blue one, I need something suitable for winter"
    llm = StubLLM([
        operation("remove", "color", "blue", "forget the blue one"),
        operation("add", "use_case", "winter", "suitable for winter"),
    ])
    state = SessionState(turn=1)
    state.add(Constraint("color: blue", "color", "blue", 1, "template"))
    state.turn = 2
    IntentPipeline(StubIndex(), llm).process(message, state, erase="delete")
    assert not any(item.alive and item.attribute == "color" for item in state.constraints)
    assert any(item.alive and item.value == "winter" for item in state.constraints)
    assert state.override_seen


def test_dad_message_still_extracts_explicit_xl():
    message = "It's for my dad; he normally wears around an XL"
    llm = StubLLM([operation("add", "size", "XL", "XL", strength="soft")])
    state = SessionState(turn=1)
    IntentPipeline(StubIndex(), llm).process(message, state)
    assert state.slots["size"] == ["xl"]
    assert next(iter(state.live())).text == "XL"


def test_negative_style_becomes_an_exclusion():
    message = "Nothing too dressy"
    llm = StubLLM([operation("add", "style", "dressy", "dressy", polarity="avoid")])
    state = SessionState(turn=1)
    IntentPipeline(StubIndex(), llm).process(message, state)
    assert state.exclusions["style"] == ["dressy"]
    assert state.slots == {}


def test_abroad_does_not_invent_europe():
    message = "I would prefer something shipped in from abroad"
    llm = StubLLM(
        [operation("add", "use_case", "from abroad", "from abroad")],
    )
    state = SessionState(turn=1)
    IntentPipeline(StubIndex(), llm).process(message, state)
    constraint = next(iter(state.live()))
    assert constraint.text == "Imported"
    assert "Europe" not in constraint.text


def test_unverified_replacement_neither_adds_nor_erases_state():
    message = "Actually I need an indescribable finish"
    llm = StubLLM(
        [operation("replace", "style", "indescribable", "indescribable finish")],
        [{"selected": None, "generated_query": None}],
    )
    state = SessionState(turn=1)
    state.add(Constraint("Dressy", "style", "dressy", 1, "template"))
    state.turn = 2
    IntentPipeline(StubIndex(), llm).process(message, state, erase="delete")
    assert [(item.text, item.alive) for item in state.constraints] == [("Dressy", True)]


def test_benchmark_erase_policy_demotes_instead_of_deleting():
    message = "Forget blue"
    llm = StubLLM([operation("remove", "color", "blue", "Forget blue")])
    state = SessionState(turn=1)
    state.add(Constraint("color: blue", "color", "blue", 1, "template"))
    state.turn = 2
    IntentPipeline(StubIndex(), llm).process(message, state, erase="demote")
    assert state.constraints[0].alive
    assert state.constraints[0].demoted


def test_poly_and_tees_remain_ambiguous_and_never_become_cotton():
    class AmbiguousIndex(StubIndex):
        def exact_canonical(self, attribute, value):
            return None

        def canonical_candidate_records(self, attribute, phrase, limit=8):
            assert (attribute, phrase) == ("material", "poly")
            return [
                {"label": "polyester", "attribute": "material", "value": "polyester",
                 "score": 2.0, "support": 100},
                {"label": "Polyurethane", "attribute": "material", "value": "polyurethane",
                 "score": 1.5, "support": 20},
            ]

    class AmbiguousCategories:
        def resolve_candidates(self, phrase):
            assert phrase == "tees"
            return [("Tops & Tees T-Shirts", 0.55), ("Active Shirts & Tees T-Shirts", 0.45)]

        def resolve_phrase(self, phrase):
            return None

    class RestoreLLM(StubLLM):
        def restore_template(self, message, state):
            return {
                "kind": "buying",
                "category": "tees",
                "attribute": None,
                "operations": [operation("add", "material", "poly", "poly")],
            }

    state = SessionState(turn=1)
    parse(
        "I want tees. Requirement: poly",
        state,
        intent_pipeline=IntentPipeline(AmbiguousIndex(), RestoreLLM([]), AmbiguousCategories()),
    )
    assert state.category is None
    assert len(state.category_hypotheses) == 2
    assert state.constraints == []
    assert state.restored_messages == {}
    assert len(state.ambiguities) == 1
    assert {item.value for item in state.ambiguities[0].alternatives} == {
        "polyester", "polyurethane"
    }
    assert all(item.value != "cotton" for item in state.ambiguities[0].alternatives)
