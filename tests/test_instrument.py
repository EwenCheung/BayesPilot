"""R4-A5 / R4-A6 — the offline instrument measures something MTTC does not.

The whole road rests on `FirstHit@k` being different from MTTC. If it is not, the instrument is
re-deriving a number we already had and Phase I was pointless — so that is the assertion.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.instrument import Recorder, SessionTrace, TurnTrace, early_hit_curve, shipped_curve  # noqa: E402


def _trace(turn, internal, shipped):
    return TurnTrace(turn=turn, internal_ranking=internal, shipped=shipped,
                     depth=len(shipped), stalls=0, entropy=0.0)


class TestInstrument(unittest.TestCase):
    def test_a_held_turn_still_records_a_ranking(self) -> None:
        """R4-A5: capture happens BEFORE the ship/hold decision, so depth 0 is not a blind turn.

        If it were captured after, a held turn would record nothing and the curve would silently
        collapse back into MTTC.
        """
        session = SessionTrace("s", [_trace(1, ["X", "T"], []), _trace(2, ["T", "X"], ["T"])])
        self.assertEqual(session.first_hit("T", 3), 1, "knew at turn 1 while shipping nothing")
        self.assertEqual(session.first_shipped("T"), 2)

    def test_first_hit_respects_k(self) -> None:
        session = SessionTrace("s", [_trace(1, ["A", "B", "C", "T"], [])])
        self.assertIsNone(session.first_hit("T", 3))
        self.assertEqual(session.first_hit("T", 10), 1)

    def test_missing_target_returns_none_not_zero(self) -> None:
        session = SessionTrace("s", [_trace(1, ["A"], ["A"])])
        self.assertIsNone(session.first_hit("T", 10))
        self.assertIsNone(session.first_shipped("T"))

    def test_curves_are_monotone_and_bounded(self) -> None:
        rec = Recorder()
        rec.record("a", _trace(1, ["T"], []))
        rec.record("a", _trace(2, ["T"], ["T"]))
        rec.record("b", _trace(1, ["X"], ["X"]))
        curve = early_hit_curve(rec, {"a": "T", "b": "T"}, 3)
        self.assertEqual(curve, sorted(curve), "a cumulative curve cannot go down")
        self.assertTrue(all(0.0 <= v <= 1.0 for v in curve))

    def test_early_hit_dominates_shipped(self) -> None:
        """R4-A6: the agent cannot ship what it does not internally rank, so knowing >= shipping."""
        rec = Recorder()
        rec.record("a", _trace(1, ["T"], []))
        rec.record("a", _trace(2, ["T"], ["T"]))
        targets = {"a": "T"}
        for knew, shipped in zip(early_hit_curve(rec, targets, 10), shipped_curve(rec, targets)):
            self.assertGreaterEqual(knew, shipped)


if __name__ == "__main__":
    unittest.main()
