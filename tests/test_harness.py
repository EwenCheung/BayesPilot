"""Spec 3.10 / A8 — we must grade ourselves with the referee's own arithmetic."""
import json
from pathlib import Path

from src.eval import compare, harness

KIT = Path(__file__).parent.parent / "techjam-conversational-search-main"


def session(hit, rank, turn, scenario="buying"):
    return {"sample_id": "x", "scenario_type": scenario, "hit": hit, "first_hit_turn": turn,
            "best_rank": rank, "reciprocal_rank": 0.0 if rank is None else 1.0 / rank}


def test_technical_score_matches_the_evaluators_formula():
    sessions = [session(True, 1, 1), session(True, 2, 3), session(False, None, None)]
    hit, mrr, mttc = 2 / 3, (1.0 + 0.5 + 0.0) / 3, (1 + 3 + 11) / 3
    expected = 0.50 * hit + 0.30 * mrr + 0.20 * max(0.0, min(1.0, (11 - mttc) / 10))
    assert abs(compare.technical_score(sessions) - expected) < 1e-12


def test_bootstrap_is_seed_deterministic_and_brackets_the_point_estimate():
    sessions = [session(True, 1, 1) for _ in range(90)] + [session(False, None, None) for _ in range(10)]
    low, high = compare.bootstrap(sessions, resamples=200, seed=7)
    assert (low, high) == compare.bootstrap(sessions, resamples=200, seed=7)
    assert low <= compare.technical_score(sessions) <= high


def test_kit_manifest_covers_the_files_a_score_depends_on():
    harness.ensure_manifest()
    manifest = json.loads(harness.MANIFEST.read_text())
    assert "evaluator/local_evaluator.py" in manifest and "data/public_set.jsonl" in manifest
    harness.verify_kit()  # raises if the kit has drifted
