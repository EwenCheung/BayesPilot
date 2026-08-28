"""Spec 3.1 — our copied simulator functions must match the referee's exactly.

Tests may import the evaluator; the agent may not (spec C2). Drift here silently
invalidates every downstream measurement, so this is the highest-value test we have.
"""
import json
import random
from pathlib import Path

import pytest

from evaluator import local_evaluator as ref
from src.common import simulator as ours

CATALOG = Path(__file__).parent.parent / "techjam-conversational-search-main" / "data" / "catalog.jsonl"
SAMPLE = 2000


@pytest.fixture(scope="module")
def products():
    rows = [json.loads(line) for line in CATALOG.open(encoding="utf-8")]
    return random.Random(0).sample(rows, SAMPLE)


def test_intent_card_matches_reference(products):
    for product in products:
        assert ours.intent_card(product) == ref.intent_card(product), product["parent_asin"]


def test_coarse_category_matches_reference(products):
    for product in products:
        values = [str(v) for v in product.get("categories") or []]
        assert ours.coarse_category(values) == ref.coarse_category(values)


def test_searchable_text_matches_reference(products):
    for product in products:
        assert ours.searchable_text(product) == ref.searchable_text(product)


def test_classify_constraint_matches_reference(products):
    for product in products:
        card = ref.intent_card(product)
        for value in card["hard_constraints"] + card["soft_preferences"]:
            assert ours.classify_constraint(value) == ref.classify_constraint(value), value


def test_agent_tree_never_imports_the_evaluator():
    """Spec C2 — the evaluator imports starter.agent, so importing it back is a hard crash."""
    import ast

    for path in (Path(__file__).parent.parent / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not any("local_evaluator" in name or name == "evaluator" for name in names), path
