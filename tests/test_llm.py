"""Spec 3.5 / C7 / C8 — the LLM client must fail loudly into a counter and quietly into a fallback."""
import json

import pytest

from src.understand.llm import LLMClient


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
    body = json.dumps({"constraints": [{"attribute": "material", "value": "leather"},
                                       {"attribute": "color", "value": "black"}]})
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload(body)))
    pairs = client.extract("something in black leather please")
    assert ("material", "leather") in [(a, v) for a, v, _ in pairs]


def test_extract_survives_unparseable_output(tmp_path):
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload("I think maybe leather?")))
    assert client.extract("x") == []
    assert client.failures == 1


def test_rerank_returns_a_permutation_or_nothing(tmp_path):
    candidates = ["A1", "A2", "A3"]
    client = LLMClient(cache_dir=tmp_path / "good", transport=FakeTransport(chat_payload("[3, 1, 2]")))
    assert client.rerank("query", candidates) == ["A3", "A1", "A2"]

    bad = LLMClient(cache_dir=tmp_path / "bad", transport=FakeTransport(chat_payload("[9, 9, 9]")))
    assert bad.rerank("query", candidates) is None, "a malformed permutation must fall back, not corrupt the list"


def test_model_ids_are_pinned_not_aliases(tmp_path):
    """IMPORTANT.md §13.1.4 — `default`, `test`, `ornith1.0:35b` are aliases that get repointed."""
    client = LLMClient(cache_dir=tmp_path, transport=FakeTransport(chat_payload("ok")))
    assert client.chat_model not in {"default", "test", "advanced-vision", "ornith1.0:35b"}
    assert ":" in client.chat_model
