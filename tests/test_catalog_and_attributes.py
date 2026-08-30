"""Spec 3.2 / 3.3 — the index is read-only and pool-scoped; normalisation never raises."""
import json
from pathlib import Path

import pytest

from src.common.attributes import normalise
from src.r1.catalog import CatalogIndex

CATALOG = Path(__file__).parent.parent / "techjam-conversational-search-main" / "data" / "catalog.jsonl"


@pytest.fixture(scope="session")
def index():
    return CatalogIndex(CATALOG)


def test_index_covers_the_whole_catalog(index):
    assert len(index.popularity) == 50000
    assert sum(len(pool) for pool in index.by_category.values()) == 50000


def test_unknown_category_falls_back_to_a_non_empty_pool(index):
    """Spec 3.2 — an unknown category must never yield an empty set."""
    assert len(index.pool("no such category exists")) > 0


def test_card_strings_are_the_simulator_card(index):
    from src.common.simulator import intent_card

    rows = [json.loads(line) for _, line in zip(range(200), CATALOG.open(encoding="utf-8"))]
    for product in rows:
        card = intent_card(product)
        expected = set(card["hard_constraints"]) | set(card["soft_preferences"])
        assert set(index.card_strings[product["parent_asin"]]) == expected
        assert list(index.card_strings[product["parent_asin"]])[:2] == card["hard_constraints"][:2], \
            "order matters: customer_reply reveals the first two undisclosed in card order"


def test_pool_features_are_cached_and_stable(index):
    category = next(iter(index.by_category))
    first = index.pool_features(category)
    assert index.pool_features(category) is first


@pytest.mark.parametrize(
    "text,attribute,value",
    [
        ("Material: alloy", "material", "alloy"),
        ("color: black", "color", "black"),
        ("cotton", "material", "cotton"),
        ("100% Polyester", "material", "polyester"),
        ("Department: Womens", "style", "womens"),
        ("budget around $19.99", "budget", "19.99"),
    ],
)
def test_normalise_extracts_the_expected_pair(text, attribute, value):
    pairs = normalise(text)
    assert (attribute, value) in pairs, pairs


def test_normalise_never_raises_and_always_returns_something():
    for text in ["", "   ", "???", "a" * 500, "Closure type:", ":", "1234"]:
        assert isinstance(normalise(text), list)


def test_normalise_is_paraphrase_tolerant():
    """The point of the ontology: reworded text yields the same pair as the template form."""
    assert set(normalise("Material: alloy")) & set(normalise("made of alloy"))
    assert set(normalise("color: black")) & set(normalise("I'd like it in black"))


def test_hedge_widens_only_when_the_category_is_uncertain(index):
    """Spec 3.2 — a verbatim category is used exactly; an ambiguous one becomes a union pool."""
    exact = index.hedge("I'm looking for Shirts T-Shirts, but I'm still exploring.")
    assert exact == "Shirts T-Shirts"
    assert len(index.pool(exact)) == len(index.by_category["Shirts T-Shirts"])

    fuzzy = index.hedge("I need a wallet or card holder made of leather")
    assert fuzzy is not None
    assert len(index.pool(fuzzy)) > 0


def test_hedged_pool_is_capped_and_cached(index):
    key = index.hedge("necklace jewelry made of alloy")
    pool = index.pool(key)
    assert 0 < len(pool) <= 4000
    assert index.pool(key) is pool
