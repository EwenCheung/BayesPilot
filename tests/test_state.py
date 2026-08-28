"""R2-A2: state accumulates across turns and ERASES on override rather than stacking."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.state import SessionState, parse  # noqa: E402


class TestParsing(unittest.TestCase):
    def test_buying_opening_yields_category_and_hard_constraint(self) -> None:
        """R2-A2: the buying template gives us a category and one constraint on turn 1."""
        s = parse("I'm looking for Jewelry Necklaces. A key requirement is: Material:alloy.",
                  SessionState(), 1)
        self.assertEqual(s.category, "Jewelry Necklaces")
        self.assertEqual(s.values(), ["Material:alloy"])

    def test_browsing_opening_yields_category_only(self) -> None:
        """R2-A2: browsing turn 1 reveals a category and nothing else."""
        s = parse("I'm looking for Basketball Men, but I'm still exploring.", SessionState(), 1)
        self.assertEqual(s.category, "Basketball Men")
        self.assertEqual(s.values(), [])

    def test_reply_splits_two_constraints(self) -> None:
        """R2-A2: 'other' returns two constraints joined by '; ' and both must land."""
        s = SessionState(category="Belts")
        parse("For that, what matters is: 100% Leather; Buckle closure.", s, 2)
        self.assertEqual(s.values(), ["100% Leather", "Buckle closure"])

    def test_accumulation_across_turns(self) -> None:
        """R2-A2: information accumulates — turn 3 does not erase turn 1."""
        s = parse("I'm looking for Belts. A key requirement is: leather.", SessionState(), 1)
        parse("For that, what matters is: Buckle closure; color: black.", s, 2)
        self.assertEqual(s.values(), ["leather", "Buckle closure", "color: black"])
        self.assertEqual(len(s.slots["material"]), 1)

    def test_override_erases_the_superseded_preference(self) -> None:
        """R2-A2: override REPLACES the opening soft preference, it does not stack a contradiction."""
        s = parse("I'm looking for Accessories Belts. Buckle closure", SessionState(), 1)
        self.assertEqual(s.values(), ["Buckle closure"])
        parse("Actually, ignore my earlier preference. What I need is: leather.", s, 3)
        self.assertNotIn("Buckle closure", s.values())
        self.assertIn("leather", s.values())
        self.assertTrue(s.override_seen)

    def test_override_keeps_constraints_earned_by_asking(self) -> None:
        """R2-A2: only the superseded opening preference is erased; elicited replies survive."""
        s = parse("I'm looking for Belts. Buckle closure", SessionState(), 1)
        parse("For that, what matters is: 100% Leather; Made in USA.", s, 2)
        parse("Actually, ignore my earlier preference. What I need is: alloy.", s, 3)
        self.assertNotIn("Buckle closure", s.values())
        self.assertIn("100% Leather", s.values())
        self.assertIn("Made in USA", s.values())

    def test_barren_attribute_is_recorded(self) -> None:
        """R2-A2: a dead-end attribute is remembered so we never spend another turn on it."""
        s = SessionState(category="Belts")
        parse("I don't have an additional preference for material.", s, 2)
        self.assertIn("material", s.barren)
        self.assertEqual(s.values(), [])

    def test_boundary_no_preference_reveals_nothing(self) -> None:
        """R2-A2: the boundary sentence must not be mistaken for a constraint."""
        s = SessionState(category="Watches")
        parse("I don't have a preference for color; please use your judgment.", s, 2)
        self.assertEqual(s.values(), [])
        self.assertIn("color", s.barren)

    def test_null_ask_reply_reveals_nothing(self) -> None:
        """R2-A2: the ask_attribute=null reply carries no information."""
        s = SessionState(category="Watches")
        parse("Those options are not quite right yet. Ask me about one specific attribute.", s, 2)
        self.assertEqual(s.values(), [])

    def test_duplicate_constraint_is_not_double_counted(self) -> None:
        """R2-A2: re-hearing a disclosed string must not inflate the evidence."""
        s = SessionState(category="Belts")
        parse("For that, what matters is: leather.", s, 2)
        parse("For that, what matters is: leather.", s, 3)
        self.assertEqual(s.values(), ["leather"])


class TestParaphraseTolerance(unittest.TestCase):
    """The private set may be reworded. Templates stop firing; constraints must still land."""

    def test_reworded_opening_still_yields_a_category(self) -> None:
        """R2-A2: a rewritten carrier sentence must not cost us the candidate pool."""
        s = parse("Hi! I want Jewelry Necklaces, just browsing for now", SessionState(), 1)
        self.assertIsNotNone(s.category)
        self.assertIn("Jewelry Necklaces", s.category)

    def test_reworded_reply_still_yields_constraints(self) -> None:
        """R2-A2: a rewritten answer must still deposit its payload into the slots."""
        s = SessionState(category="Belts")
        parse("Honestly it has to be 100% Leather", s, 2)
        self.assertIn("100% Leather", s.values())

    def test_reworded_override_still_erases(self) -> None:
        """R2-A2: override detection must not depend on the exact template sentence."""
        s = parse("I'm looking for Belts. Buckle closure", SessionState(), 1)
        parse("Actually, forget that — what I need is leather", s, 3)
        self.assertNotIn("Buckle closure", s.values())
        self.assertTrue(s.override_seen)


class TestSlotDecay(unittest.TestCase):
    def test_slot_age_grows_with_turns(self) -> None:
        """R2-A2: slot_age tracks staleness (PROBLEM.md §4.3 'slot decay over time')."""
        s = parse("I'm looking for Belts. A key requirement is: leather.", SessionState(), 1)
        s.turn = 4
        self.assertEqual(s.slot_age["material"], 3)

    def test_decay_weight_falls_with_age_and_disables_at_zero(self) -> None:
        """R2-A2: decay down-weights stale evidence; decay=0 is the ablation."""
        s = parse("I'm looking for Belts. A key requirement is: leather.", SessionState(), 1)
        s.turn = 4
        c = s.constraints[0]
        self.assertLess(s.weight_of(c, decay=0.3), 1.0)
        self.assertEqual(s.weight_of(c, decay=0.0), 1.0)


if __name__ == "__main__":
    unittest.main()
