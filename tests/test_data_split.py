from __future__ import annotations

from scripts.split_train_dev import split_rows


def _row(index: int, scenario: str) -> dict:
    return {
        "sample_id": f"s{index:03d}",
        "scenario_type": scenario,
        "ground_truth": {"parent_asin": f"A{index:03d}"},
    }


def test_split_is_exact_stratified_disjoint_and_deterministic() -> None:
    rows = []
    for scenario in ("buying", "browsing", "intent_override", "boundary"):
        start = len(rows)
        rows.extend(_row(start + index, scenario) for index in range(10))

    first = split_rows(rows, seed=7)
    second = split_rows(rows, seed=7)
    assert first == second
    assert {name: len(selected) for name, selected in first.items()} == {
        "train": 24,
        "validation": 8,
        "test": 8,
    }
    for selected in first.values():
        counts = {}
        for row in selected:
            counts[row["scenario_type"]] = counts.get(row["scenario_type"], 0) + 1
        expected = 6 if len(selected) == 24 else 2
        assert set(counts.values()) == {expected}

    id_sets = [{row["sample_id"] for row in selected} for selected in first.values()]
    target_sets = [{row["ground_truth"]["parent_asin"] for row in selected} for selected in first.values()]
    assert all(not id_sets[i] & id_sets[j] for i in range(3) for j in range(i + 1, 3))
    assert all(not target_sets[i] & target_sets[j] for i in range(3) for j in range(i + 1, 3))
