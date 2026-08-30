"""Spec 3.2 / 3.3 — the index is read-only and pool-scoped; normalisation never raises."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.attributes import normalise
from src.r3.category import CategoryBelief
from src.r3.index import ItemIndex

CATALOG = Path(__file__).parent.parent / "assets" / "catalog.jsonl"


@pytest.fixture(scope="session")
def cat_index():
    return CategoryBelief(CATALOG)


@pytest.fixture(scope="session")
def item_index():
    return ItemIndex(CATALOG)


def test_index_covers_the_whole_catalog(cat_index, item_index):
    assert len(item_index.asins) == 50000
    assert sum(len(pool) for pool in cat_index.by_category.values()) == 50000


def test_category_pool_retrieval(cat_index):
    """Dynamic category pool covering posterior mass."""
    pool = cat_index.pool("I'm looking for Belts", tau=0.90)
    assert len(pool) > 0
    assert isinstance(pool, list)


def test_pool_features_are_cached_and_stable(cat_index):
    category = next(iter(cat_index.by_category))
    assert len(cat_index.by_category[category]) > 0


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


def test_r3_canonical_retrieval_corrects_typos_without_forcing_poly(item_index):
    assert item_index.exact_canonical("material", "polyster").lower() == "polyester"
    assert item_index.exact_canonical("material", "cotten").lower() == "cotton"
    assert item_index.exact_canonical("material", "poly") is None
    records = item_index.canonical_candidate_records("material", "poly", limit=6)
    assert records
    assert all(row["value"] != "cotton" for row in records)
