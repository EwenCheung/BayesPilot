"""Spec 3.5 / C7 / C8 — the LLM client must fail loudly into a counter and quietly into a fallback."""
import json

import pytest

from src.common.llm import INTENT_SYSTEM, LLMClient


@pytest.fixture(autouse=True)
def _unit_tests_control_offline_mode(monkeypatch):
    """Do not let a benchmark-level R3_OFFLINE setting bypass fake transports in unit tests."""
    monkeypatch.delenv("R3_OFFLINE", raising=False)


class FakeTransport:
    """Stands in for the network. Records calls, replays canned payloads."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def __call__(self, path, body, timeout):
        self.calls.append((path, body))
        payload = self.payloads.pop(0) if self.payloads else self.payloads
        if isinstance(payload, Exception):
            raise payload
        return payload


def chat_payload(content):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def test_offline_mode_never_touches_the_network(tmp_path):
    transport = FakeTransport()
    client = LLMClient(cache_dir=tmp_path, offline=True, transport=transport)
    assert client.chat([{"role": "user", "content": "hi"}]) is None
    assert client.extract("black leather boots") == []
    assert transport.calls == []
    assert client.failures == 0, "an intentional offline skip is not a failure"


def test_empty_content_counts_as_a_failure(tmp_path):
    """IMPORTANT.md §13.1.3 — a model returning content:None burned days once. Never again."""
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload(None), chat_payload("")))
    assert client.chat([{"role": "user", "content": "hi"}]) is None
    assert client.chat([{"role": "user", "content": "hi2"}]) is None
    assert client.failures == 2


def test_network_error_is_caught_and_counted(tmp_path):
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(RuntimeError("boom")))
    assert client.chat([{"role": "user", "content": "hi"}]) is None
    assert client.failures == 1


def test_successful_call_is_cached_on_disk(tmp_path):
    transport = FakeTransport(chat_payload("ok"))
    client = LLMClient(cache_dir=tmp_path, transport=transport)
    messages = [{"role": "user", "content": "hi"}]
    assert client.chat(messages) == "ok"
    assert client.chat(messages) == "ok"
    assert len(transport.calls) == 1, "second identical call must be served from cache"
    assert client.prompt_tokens == 10 and client.completion_tokens == 5


def test_extract_parses_json_pairs(tmp_path):
    body = json.dumps({"operations": [
        {"op": "add", "attribute": "material", "value": "leather"},
        {"op": "add", "attribute": "color", "value": "black"},
    ]})
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload(body)))
    pairs = client.extract("something in black leather please")
    assert ("material", "leather") in [(a, v) for a, v, _ in pairs]


def test_extract_survives_unparseable_output(tmp_path):
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload("I think maybe leather?")))
    assert client.extract("x") == []
    assert client.failures == 1


def test_typed_intent_operations_and_canonical_selection(tmp_path):
    operations = json.dumps({"operations": [{
        "op": "remove", "attribute": "color", "value": "blue",
        "evidence": "forget blue", "confidence": 0.99,
    }]})
    selected = json.dumps({"choice": 2, "generated_query": None})
    client = LLMClient(
        cache_dir=tmp_path,
        transport=FakeTransport(chat_payload(operations), chat_payload(selected)),
    )
    assert client.interpret_operations("forget blue", {"active": []})[0]["op"] == "remove"
    resolved = client.resolve_canonical(
        "material", "entirely cotton", ["Cotton blend", "100% Cotton"], allow_generate=True
    )
    assert resolved == {"selected": "100% Cotton", "generated_query": None}


def test_generated_canonical_text_is_only_a_retrieval_query(tmp_path):
    body = json.dumps({"choice": None, "generated_query": "Machine washable"})
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload(body)))
    resolved = client.resolve_canonical("use_case", "washer safe", [], allow_generate=True)
    assert resolved == {"selected": None, "generated_query": "Machine washable"}


def test_rerank_returns_a_permutation_or_nothing(tmp_path):
    candidates = ["A1", "A2", "A3"]
    client = LLMClient(cache_dir=tmp_path / "good", transport=FakeTransport(chat_payload("[3, 1, 2]")))
    assert client.rerank("query", candidates) == ["A3", "A1", "A2"]

    bad = LLMClient(cache_dir=tmp_path / "bad", transport=FakeTransport(chat_payload("[9, 9, 9]")))
    assert bad.rerank("query", candidates) is None, "a malformed permutation must fall back, not corrupt the list"


def test_llm_selects_one_unknown_answerable_attribute(tmp_path):
    body = json.dumps({"ask_attribute": "size"})
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload(body)))
    attribute = client.select_attribute(
        {"preference_tags": ["style"]},
        {"known_slots": {"use_case": ["wedding"]}, "known_attributes": ["use_case"],
         "missing_attributes": ["size", "material"], "exhausted": []},
    )
    assert attribute == "size"
    assert client.totals() == (10, 5)


def test_llm_selector_rejects_known_or_exhausted_attribute(tmp_path):
    body = json.dumps({"ask_attribute": "budget"})
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload(body)))
    assert client.select_attribute(
        {}, {"known_slots": {"budget": ["50"]}, "known_attributes": ["budget"],
             "missing_attributes": ["size"], "exhausted": []},
    ) is None
    assert client.failures == 1


def test_model_ids_are_pinned_not_aliases(tmp_path):
    """IMPORTANT.md §13.1.4 — `default`, `test`, `ornith1.0:35b` are aliases that get repointed."""
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload("ok")))
    assert client.chat_model not in {"default", "test", "advanced-vision", "ornith1.0:35b"}
    assert ":" in client.chat_model


def test_restoration_prompt_requires_context_typos_and_ambiguity_groups():
    lowered = INTENT_SYSTEM.lower()
    assert '"route":"deterministic|hybrid"' in lowered
    assert '"normalized_text"' in lowered
    assert "always choose one route" in lowered
    assert "entire current state" in lowered
    assert "misspellings" in lowered
    assert "slang" in lowered
    assert "ambiguous" in lowered
    assert '"group"' in lowered
    assert '"poly"' in lowered
