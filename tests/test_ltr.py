"""Tests for the Learning-to-Rank (LTR) module."""
from __future__ import annotations

import math
import numpy as np
import pytest
from src.common.contracts import Constraint, SessionState
from src.r3.ltr import FEATURE_NAMES, LTRRanker, extract_features


class FakeIndex:
    def __init__(self, items: dict[str, str]):
        self.lexical_text = items
        self.title = {a: t for a, t in items.items()}
        self.log_pop = {a: math.log1p(i + 1) for i, a in enumerate(items)}
        self.spec = {a: tuple(t.split()) for a, t in items.items()}
        self.card = {a: tuple(t.split()) for a, t in items.items()}
        self._pairs = {a: frozenset([("color", "blue"), ("material", "cotton")]) if "cotton" in items[a] else frozenset() for a in items}
        self._tokens = {a: frozenset(t.split()) for a, t in items.items()}

    def pairs(self, asin: str):
        return self._pairs.get(asin, frozenset())

    def tokens(self, asin: str):
        return self._tokens.get(asin, frozenset())


@pytest.fixture
def fake_index():
    return FakeIndex({
        "A001": "cotton blue casual t-shirt",
        "A002": "polyester black running shorts",
        "A003": "wool red winter sweater",
    })


def test_extract_features_shape(fake_index):
    state = SessionState()
    state.add(Constraint(text="cotton", attribute="material", value="cotton", turn=1, tier="template"))
    candidates = ["A001", "A002", "A003"]

    X = extract_features(
        fake_index,
        candidates,
        state,
        query_raw="I want blue cotton t-shirt",
        query_norm="I want blue cotton t-shirt",
        top_category="t-shirt",
    )

    assert X.shape == (3, len(FEATURE_NAMES))
    # A001 has highest exact & token match
    assert X[0, 1] >= X[1, 1]  # exact_card_matches
    assert X[0, 3] > X[1, 3]   # token_overlap


def test_ltr_ranker_fit_predict_rank():
    # Synthetic dataset
    X_train = np.array([
        [1.0, 3.0, 2.0, 0.9, 0.8, 0.8, 0.8, 1.0],  # Positive
        [0.2, 0.0, 0.0, 0.1, 0.0, 0.1, 0.1, 0.0],  # Negative
        [0.5, 1.0, 0.0, 0.4, 0.3, 0.4, 0.4, 0.0],  # Medium
    ], dtype=np.float32)
    y_train = np.array([1.0, 0.0, 0.5], dtype=np.float32)

    ranker = LTRRanker(model_type="ridge")
    ranker.fit(X_train, y_train)

    preds = ranker.predict(X_train)
    assert preds[0] > preds[1]

    candidates = ["A001", "A002", "A003"]
    ranked = ranker.rank(candidates, X_train)
    assert ranked[0] == "A001"
    assert ranked[-1] == "A002"


def test_ltr_ranker_save_load(tmp_path):
    X_train = np.array([[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]], dtype=np.float32)
    y_train = np.array([1.0], dtype=np.float32)

    ranker = LTRRanker(model_type="ridge")
    ranker.fit(X_train, y_train)

    save_path = tmp_path / "ltr_model.pkl"
    ranker.save(save_path)

    loaded = LTRRanker.load(save_path)
    assert loaded._is_fitted
    np.testing.assert_allclose(ranker.predict(X_train), loaded.predict(X_train))
