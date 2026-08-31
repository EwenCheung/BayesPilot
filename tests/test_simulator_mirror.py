"""Spec 3.1 — our copied simulator functions must match the referee's exactly.

Tests may import the evaluator; the agent may not (spec C2). Drift here silently
invalidates every downstream measurement, so this is the highest-value test we have.
"""
import json
import random
from pathlib import Path

import pytest

from evaluator import local_evaluator as ref
from src import simulator as ours

CATALOG = Path(__file__).parent.parent / "data" / "catalog.jsonl"
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


AGENT_TREES = ("common", "r1", "r2", "r3")


def _imported_names(path):
    import ast
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            yield node.module or ""


def _agent_modules():
    src = Path(__file__).parent.parent / "src"
    for tree in AGENT_TREES:
        yield from (src / tree).rglob("*.py")


def test_agent_tree_never_imports_the_evaluator():
    """Spec C2 — the evaluator imports starter.agent, so importing it back is a hard crash.

    ⚠️ Scoped to the AGENT trees, not all of `src/`. `src/eval/` runs the evaluator in-process and
    must import it; it sits outside the cycle because no agent module reaches it — which is exactly
    what `test_agent_tree_never_imports_the_harness` below keeps true. Narrowing this test without
    that second one would open the hole it exists to close.
    """
    for path in _agent_modules():
        for name in _imported_names(path):
            assert "local_evaluator" not in name and name != "evaluator", path


def test_agent_tree_never_imports_the_harness():
    """Spec C2 — the exemption above holds only while agent code cannot reach `src.eval`.

    `src/eval/harness.py` imports the evaluator. If an agent module ever imports anything under
    `src.eval`, the circular import returns by the back door and the agent crashes at startup.
    """
    for path in _agent_modules():
        for name in _imported_names(path):
            assert not name.startswith("src.eval") and name != "..eval", path
