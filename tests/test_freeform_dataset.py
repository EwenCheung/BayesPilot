from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from src.eval.freeform import STYLES, is_official_grammar, rewrite_message


ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "techjam-conversational-search-main"
DATA = KIT / "data" / "freeform_v1"
EXPECTED_EVALUATOR_HASH = "79a5ea06f9a1b8c5036f30efa85dc1f36b8f6b06eb8feb8f545dfa767bc45564"
EXPECTED_COUNTS = {
    "train": {"buying": 480, "browsing": 480, "intent_override": 180, "boundary": 60},
    "validation": {"buying": 160, "browsing": 160, "intent_override": 60, "boundary": 20},
    "test": {"buying": 320, "browsing": 320, "intent_override": 120, "boundary": 40},
}


def rows(split: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / f"{split}.jsonl").read_text().splitlines()]


def test_official_local_evaluator_is_byte_identical() -> None:
    path = KIT / "evaluator" / "local_evaluator.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED_EVALUATOR_HASH


def test_freeform_split_sizes_and_scenarios() -> None:
    for split, expected in EXPECTED_COUNTS.items():
        selected = rows(split)
        assert len(selected) == sum(expected.values())
        assert Counter(row["scenario_type"] for row in selected) == expected


def test_every_stored_initial_message_is_non_template() -> None:
    for split in EXPECTED_COUNTS:
        for row in rows(split):
            variant = row["free_form"]
            assert variant["style"] in STYLES
            assert variant["initial_message"].strip()
            assert not is_official_grammar(variant["initial_message"]), row["sample_id"]


def test_freeform_targets_do_not_cross_splits() -> None:
    targets = {
        split: {row["ground_truth"]["parent_asin"] for row in rows(split)}
        for split in EXPECTED_COUNTS
    }
    assert not targets["train"] & targets["validation"]
    assert not targets["train"] & targets["test"]
    assert not targets["validation"] & targets["test"]
    assert all(len(targets[split]) == sum(EXPECTED_COUNTS[split].values()) for split in targets)


def test_test_split_covers_many_product_categories() -> None:
    manifest = json.loads((DATA / "manifest.json").read_text())
    assert manifest["splits"]["test"]["unique_coarse_categories"] >= 250


def test_all_official_turn_kinds_are_rewritten() -> None:
    messages = (
        "I'm looking for Shirts T-Shirts. A key requirement is: Material: cotton.",
        "I'm looking for Dresses Casual, but I'm still exploring.",
        "For that, what matters is: color: black; Closure type: Buckle.",
        "Actually, ignore my earlier preference. What I need is: Material: alloy.",
        "I don't have a preference for color; please use your judgment.",
        "I don't have an additional preference for size.",
        "Those options are not quite right yet. Ask me about one specific attribute.",
    )
    for index, message in enumerate(messages):
        rewritten = rewrite_message(message, seed=10 + index, turn=index + 1)
        assert rewritten != message
        assert not is_official_grammar(rewritten)


def test_test_split_requires_explicit_acknowledgement() -> None:
    source = (ROOT / "scripts" / "evaluate_freeform.py").read_text(encoding="utf-8")
    assert "--acknowledge-sealed-test" in source
    assert "from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl" in source
