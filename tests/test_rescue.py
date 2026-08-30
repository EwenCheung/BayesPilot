"""Tests for the rescue module: global retrieval, union, and RRF."""
from __future__ import annotations

import math
import pytest
from unittest.mock import MagicMock
from src.r3.rescue import (
    GlobalLexicalRescue,
    GlobalSemanticRescue,
    candidate_union,
    reciprocal_rank_fusion,
)


# --------------- fixtures ---------------

class FakeIndex:
    """Minimal mock of ItemIndex for testing."""
    def __init__(self, items: dict[str, str]):
        self.lexical_text = items
        self.title = {a: t for a, t in items.items()}
        self.log_pop = {a: math.log1p(i) for i, a in enumerate(items)}
        self.spec = {a: () for a in items}
        self.card = {a: () for a in items}


@pytest.fixture
def small_index():
    return FakeIndex({
        "A001": "cotton tee shirt blue casual",
        "A002": "polyester running shorts black",
        "A003": "silk formal dress red evening",
        "A004": "cotton hoodie green casual streetwear",
        "A005": "leather boots brown hiking waterproof",
        "A006": "wool sweater grey winter warm knit",
    })


# --------------- GlobalLexicalRescue ---------------

class TestGlobalLexicalRescue:
    def test_basic_rescue(self, small_index):
        rescue = GlobalLexicalRescue(small_index)
        results = rescue.rescue("cotton casual", top_k=3)
        # Should find cotton items
        asins = [a for a, _ in results]
        assert "A001" in asins or "A004" in asins
        assert len(results) <= 3

    def test_empty_query_returns_empty(self, small_index):
        rescue = GlobalLexicalRescue(small_index)
        assert rescue.rescue("") == []
        assert rescue.rescue("   ") == []

    def test_exclude_works(self, small_index):
        rescue = GlobalLexicalRescue(small_index)
        results_full = rescue.rescue("cotton casual", top_k=10)
        results_excl = rescue.rescue("cotton casual", top_k=10, exclude={"A001"})
        full_asins = {a for a, _ in results_full}
        excl_asins = {a for a, _ in results_excl}
        assert "A001" not in excl_asins
        if "A001" in full_asins:
            assert len(excl_asins) < len(full_asins)

    def test_scores_sorted_descending(self, small_index):
        rescue = GlobalLexicalRescue(small_index)
        results = rescue.rescue("cotton casual blue tee")
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i][1] >= results[i + 1][1]

    def test_top_k_limit(self, small_index):
        rescue = GlobalLexicalRescue(small_index)
        results = rescue.rescue("cotton casual blue tee", top_k=2)
        assert len(results) <= 2


# --------------- GlobalSemanticRescue ---------------

class TestGlobalSemanticRescue:
    def test_none_semantics_returns_empty(self):
        rescue = GlobalSemanticRescue(None)
        assert rescue.rescue("test query") == []

    def test_empty_query_returns_empty(self):
        import numpy as np
        mock_semantics = MagicMock()
        mock_semantics.asins = ["A001", "A002"]
        mock_semantics._row = {"A001": 0, "A002": 1}
        mock_semantics._vectors = np.array([[1, 0], [0, 1]], dtype=np.float32)
        mock_semantics.encode.return_value = np.zeros(2, dtype=np.float32)
        rescue = GlobalSemanticRescue(mock_semantics)
        assert rescue.rescue("") == []

    def test_basic_rescue_with_mock(self):
        import numpy as np
        mock_semantics = MagicMock()
        mock_semantics.asins = ["A001", "A002", "A003"]
        mock_semantics._row = {"A001": 0, "A002": 1, "A003": 2}
        vecs = np.array([[1, 0], [0.5, 0.5], [0, 1]], dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        mock_semantics._vectors = vecs / norms
        mock_semantics.encode.return_value = np.array([1, 0], dtype=np.float32)
        rescue = GlobalSemanticRescue(mock_semantics)
        results = rescue.rescue("test")
        assert len(results) > 0
        # A001 should rank highest (vector [1,0] matches query [1,0])
        assert results[0][0] == "A001"

    def test_exclude_works(self):
        import numpy as np
        mock_semantics = MagicMock()
        mock_semantics.asins = ["A001", "A002"]
        mock_semantics._row = {"A001": 0, "A002": 1}
        mock_semantics._vectors = np.array([[1, 0], [0, 1]], dtype=np.float32)
        mock_semantics.encode.return_value = np.array([1, 0], dtype=np.float32)
        rescue = GlobalSemanticRescue(mock_semantics)
        results = rescue.rescue("test", exclude={"A001"})
        asins = {a for a, _ in results}
        assert "A001" not in asins


# --------------- candidate_union ---------------

class TestCandidateUnion:
    def test_union_no_rescue(self):
        pool = ["A", "B", "C"]
        assert candidate_union(pool, []) == ["A", "B", "C"]

    def test_union_adds_rescue(self):
        pool = ["A", "B"]
        rescue = [[("C", 0.9), ("D", 0.8)]]
        result = candidate_union(pool, rescue)
        assert result == ["A", "B", "C", "D"]

    def test_union_deduplicates(self):
        pool = ["A", "B", "C"]
        rescue = [[("B", 0.9), ("D", 0.8)], [("A", 0.7), ("E", 0.6)]]
        result = candidate_union(pool, rescue)
        assert result == ["A", "B", "C", "D", "E"]
        assert len(result) == len(set(result))

    def test_union_preserves_pool_order(self):
        pool = ["X", "Y", "Z"]
        rescue = [[("A", 0.5)]]
        result = candidate_union(pool, rescue)
        assert result[:3] == ["X", "Y", "Z"]

    def test_union_empty_pool(self):
        rescue = [[("A", 0.5), ("B", 0.3)]]
        result = candidate_union([], rescue)
        assert result == ["A", "B"]


# --------------- reciprocal_rank_fusion ---------------

class TestReciprocalRankFusion:
    def test_single_list(self):
        ranked = reciprocal_rank_fusion(
            {"route1": ["A", "B", "C"]},
            k=60,
        )
        assert ranked == ["A", "B", "C"]

    def test_two_agreeing_lists(self):
        ranked = reciprocal_rank_fusion(
            {"r1": ["A", "B", "C"], "r2": ["A", "B", "C"]},
            k=60,
        )
        assert ranked[0] == "A"

    def test_two_disagreeing_lists(self):
        ranked = reciprocal_rank_fusion(
            {"r1": ["A", "B", "C"], "r2": ["C", "B", "A"]},
            k=60,
        )
        # Because 1/(60+x) is convex, (1/61 + 1/63) = 0.032266 > 2/62 = 0.032258.
        # A and C tie for top score, B is just behind.
        assert set(ranked[:2]) == {"A", "C"}
        assert ranked[2] == "B"

    def test_weighted_fusion(self):
        ranked = reciprocal_rank_fusion(
            {"r1": ["A", "B"], "r2": ["B", "A"]},
            weights={"r1": 10.0, "r2": 1.0},
            k=60,
        )
        # r1 has 10x weight, so A should rank first
        assert ranked[0] == "A"

    def test_zero_weight_ignored(self):
        ranked = reciprocal_rank_fusion(
            {"r1": ["A", "B"], "r2": ["C", "D"]},
            weights={"r1": 1.0, "r2": 0.0},
            k=60,
        )
        assert "C" not in ranked
        assert "D" not in ranked

    def test_absent_candidates_not_penalized(self):
        """A candidate not in a route simply gets 0 from that route, not negative."""
        ranked = reciprocal_rank_fusion(
            {"r1": ["A", "B", "C"], "r2": ["D", "E"]},
            k=60,
        )
        # All candidates should be present
        assert set(ranked) == {"A", "B", "C", "D", "E"}

    def test_default_weights(self):
        ranked = reciprocal_rank_fusion(
            {"r1": ["A", "B", "C"], "r2": ["A", "C", "B"]},
        )
        # A is rank 1 in both routes -> clear winner
        assert ranked[0] == "A"
        # B is rank 2 in r1, rank 3 in r2 -> score = 1/62 + 1/63
        # C is rank 3 in r1, rank 2 in r2 -> score = 1/63 + 1/62 (tied with B)
        assert set(ranked[1:]) == {"B", "C"}

    def test_empty_lists(self):
        ranked = reciprocal_rank_fusion({"r1": [], "r2": []})
        assert ranked == []


# --------------- Integration: all components together ---------------

class TestRescueIntegration:
    """Smoke tests ensuring the components compose correctly."""

    def test_lexical_rescue_to_union(self, small_index):
        rescue = GlobalLexicalRescue(small_index)
        pool = ["A001", "A002"]
        lex_results = rescue.rescue("leather boots hiking", top_k=5, exclude=set(pool))
        union = candidate_union(pool, [lex_results])
        # Pool items preserved
        assert "A001" in union
        assert "A002" in union
        # Should have some rescue candidates (A005 = leather boots)
        assert len(union) >= len(pool)

    def test_full_pipeline(self, small_index):
        """Test lexical rescue → union → RRF flow."""
        rescue = GlobalLexicalRescue(small_index)
        pool = ["A001", "A002"]
        lex_results = rescue.rescue("casual cotton", top_k=5)

        # Union
        union = candidate_union(pool, [lex_results])

        # RRF over pool ordering and lexical ordering
        ranked_lists = {
            "pool": pool,
            "lexical": [a for a, _ in lex_results],
        }
        fused = reciprocal_rank_fusion(ranked_lists, k=60)

        # Should have all candidates from both sources
        assert set(fused) == set(union)
