"""R4-A9 / R4-A10 — `flatness` measures how discriminating the evidence is.

The Phase S mechanism scales the popularity prior by this number, so if it does not actually separate
sharp evidence from vague evidence, the mechanism is scaling by noise.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.contracts import Constraint, SessionState  # noqa: E402
from src.r4.belief import SelectiveBelief, flatness  # noqa: E402
from src.r4.flags import Flags  # noqa: E402


class FakeIndex:
    """Minimal stand-in: `card[asin]` is the text an exact match looks for."""

    def __init__(self, cards: dict[str, str]) -> None:
        self.card = cards
        self.log_pop = {a: 1.0 for a in cards}

    def pairs(self, asin): return set()
    def tokens(self, asin): return set()


def _state(*texts: str) -> SessionState:
    state = SessionState(turn=1)
    for text in texts:
        state.add(Constraint(text=text, attribute="feature", value=text, turn=1, tier="template"))
    return state


class TestFlatness(unittest.TestCase):
    def setUp(self) -> None:
        self.flags = Flags()
        self.flags.lexical = False          # isolate the exact term

    def test_sharp_evidence_scores_near_zero(self) -> None:
        """R4-A10: one constraint isolating 1 of 100 candidates is maximally selective."""
        cards = {f"A{i}": ("leather" if i == 0 else "cotton") for i in range(100)}
        index = FakeIndex(cards)
        self.assertAlmostEqual(flatness(index, _state("leather"), list(cards), self.flags), 0.01)

    def test_vague_evidence_scores_near_one(self) -> None:
        cards = {f"A{i}": "womens" for i in range(100)}
        index = FakeIndex(cards)
        self.assertAlmostEqual(flatness(index, _state("womens"), list(cards), self.flags), 1.0)

    def test_the_most_selective_constraint_wins(self) -> None:
        """Averaging would let three vague constraints drown one sharp one."""
        cards = {f"A{i}": ("leather womens" if i == 0 else "womens") for i in range(100)}
        index = FakeIndex(cards)
        flat = flatness(index, _state("womens", "leather"), list(cards), self.flags)
        self.assertAlmostEqual(flat, 0.01, msg="the sharp constraint must dominate")

    def test_no_evidence_is_maximally_flat(self) -> None:
        """Nothing matched means the prior is the only voice — which is the risky regime."""
        cards = {f"A{i}": "cotton" for i in range(10)}
        index = FakeIndex(cards)
        self.assertEqual(flatness(index, _state("titanium"), list(cards), self.flags), 1.0)

    def test_damp_zero_leaves_the_prior_untouched(self) -> None:
        """R4-A1 depends on this: damp=0 must be bit-identical to R3's Belief."""
        index = FakeIndex({"A": "x", "B": "y"})
        plain = SelectiveBelief(index, ["A", "B"], prior_weight=0.18, damp=0.0)
        self.assertEqual(plain._prior(), {"A": 0.18, "B": 0.18})

    def test_damp_scales_the_prior_down_when_evidence_is_flat(self) -> None:
        index = FakeIndex({"A": "x", "B": "y"})
        belief = SelectiveBelief(index, ["A", "B"], prior_weight=0.18, damp=0.5)
        belief.flat = 1.0
        self.assertEqual(belief._prior(), {"A": 0.09, "B": 0.09})
        belief.flat = 0.0
        self.assertEqual(belief._prior(), {"A": 0.18, "B": 0.18})

    def test_prior_is_scaled_never_removed(self) -> None:
        """D2 / the popularity prior is still the single most valuable signal overall."""
        index = FakeIndex({"A": "x"})
        belief = SelectiveBelief(index, ["A"], prior_weight=0.18, damp=1.0)
        belief.flat = 1.0
        self.assertGreaterEqual(belief._prior()["A"], 0.0)


if __name__ == "__main__":
    unittest.main()
