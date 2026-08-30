"""Learning-to-Rank (LTR / LambdaMART) module — Step 6 in the architecture plan.

Extracts multi-channel ranking features across candidate products and ranks them using
a gradient-boosted ranking model (HistGradientBoosting / LightGBM-style) trained strictly
on training-split data.

Features per candidate item i:
  1. log_pop_norm       — popularity prior (normalized in candidate pool)
  2. exact_card_matches — count of exact matches in item's intent card
  3. attr_pair_matches  — count of (attribute, value) normalized matches
  4. token_overlap      — token-level Jaccard / overlap with query
  5. lexical_idf_score  — IDF-weighted lexical overlap score (RAWLEX surface)
  6. semantic_raw_sim   — cosine similarity with raw query (RAWSEM)
  7. semantic_norm_sim  — cosine similarity with normalized query (NORMSEM)
  8. category_match     — binary indicator: item belongs to top predicted category
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import numpy as np

from src.common.attributes import tokens
from src.common.contracts import SessionState


FEATURE_NAMES = (
    "log_pop_norm",
    "exact_card_matches",
    "attr_pair_matches",
    "token_overlap",
    "lexical_idf_score",
    "semantic_raw_sim",
    "semantic_norm_sim",
    "category_match",
)


def extract_features(
    index,
    candidates: Sequence[str],
    state: SessionState,
    query_raw: str,
    query_norm: str = "",
    semantics=None,
    lexical=None,
    top_category: str | None = None,
) -> np.ndarray:
    """Extract an N x D feature matrix for candidates."""
    n = len(candidates)
    d = len(FEATURE_NAMES)
    if n == 0:
        return np.zeros((0, d), dtype=np.float32)

    X = np.zeros((n, d), dtype=np.float32)

    # 1. Normalized popularity
    pops = [index.log_pop.get(a, 0.0) for a in candidates]
    top_pop = max(pops) if pops else 1.0
    top_pop = max(top_pop, 1.0)
    X[:, 0] = [p / top_pop for p in pops]

    # Pre-gather state constraints
    live_constraints = list(state.live())
    query_tokens = tokens(query_raw)

    # Pre-compute lexical & semantic scores if available
    lex_scores: dict[str, float] = {}
    if lexical is not None and query_raw:
        lex_scores = lexical.scores(query_raw, list(candidates))

    sem_raw_scores: dict[str, float] = {}
    if semantics is not None and query_raw:
        sem_raw_scores = semantics.scores(query_raw, list(candidates))

    sem_norm_scores: dict[str, float] = {}
    if semantics is not None and query_norm and query_norm != query_raw:
        sem_norm_scores = semantics.scores(query_norm, list(candidates))

    for idx, asin in enumerate(candidates):
        # 2. Exact card matches
        card_items = set(index.card.get(asin, ()))
        exact_count = sum(1 for c in live_constraints if c.text in card_items)
        X[idx, 1] = float(exact_count)

        # 3. Attribute pair matches
        item_pairs = index.pairs(asin)
        attr_count = sum(
            1 for c in live_constraints if (c.attribute, c.value) in item_pairs
        )
        X[idx, 2] = float(attr_count)

        # 4. Token overlap
        if query_tokens:
            item_toks = index.tokens(asin)
            overlap = len(query_tokens & item_toks) / max(1, len(query_tokens))
            X[idx, 3] = float(overlap)

        # 5. Lexical IDF score
        X[idx, 4] = float(lex_scores.get(asin, 0.0))

        # 6. Semantic raw similarity
        X[idx, 5] = float(sem_raw_scores.get(asin, 0.0))

        # 7. Semantic norm similarity
        X[idx, 6] = float(sem_norm_scores.get(asin, 0.0))

        # 8. Category match indicator
        if top_category:
            # Check if asin's lexical text or card indicates matching category
            X[idx, 7] = 1.0 if top_category.lower() in index.lexical_text.get(asin, "").lower() else 0.0

    return X


class LTRRanker:
    """Learning-to-Rank ranker with scikit-learn HistGradientBoosting / Ridge."""

    def __init__(self, model_type: str = "hist_gb") -> None:
        self.model_type = model_type
        self.model = None
        self._is_fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LTRRanker":
        """Fit ranker on feature matrix X and relevance labels y in [0, 1]."""
        if len(X) == 0:
            return self

        if self.model_type == "hist_gb":
            from sklearn.ensemble import HistGradientBoostingRegressor
            self.model = HistGradientBoostingRegressor(
                max_iter=100,
                max_depth=6,
                learning_rate=0.08,
                random_state=42,
            )
        elif self.model_type == "ridge":
            from sklearn.linear_model import Ridge
            self.model = Ridge(alpha=1.0)
        else:
            from sklearn.ensemble import GradientBoostingRegressor
            self.model = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42)

        self.model.fit(X, y)
        self._is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict relevance scores for features X."""
        if not self._is_fitted or self.model is None or len(X) == 0:
            return np.zeros(len(X), dtype=np.float32)
        return self.model.predict(X).astype(np.float32)

    def rank(
        self,
        candidates: Sequence[str],
        X: np.ndarray,
    ) -> list[str]:
        """Rank candidates in descending order of predicted LTR relevance score."""
        if len(candidates) == 0:
            return []
        if not self._is_fitted or self.model is None:
            return list(candidates)

        scores = self.predict(X)
        ranked_indices = np.argsort(-scores)
        return [candidates[i] for i in ranked_indices]

    def save(self, path: str | Path) -> None:
        """Save model to disk using pickle."""
        import pickle
        with Path(path).open("wb") as f:
            pickle.dump({"model": self.model, "type": self.model_type, "fitted": self._is_fitted}, f)

    @classmethod
    def load(cls, path: str | Path) -> "LTRRanker":
        """Load model from disk."""
        import pickle
        with Path(path).open("rb") as f:
            data = pickle.load(f)
        ranker = cls(model_type=data.get("type", "hist_gb"))
        ranker.model = data.get("model")
        ranker._is_fitted = data.get("fitted", False)
        return ranker
