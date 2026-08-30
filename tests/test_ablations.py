"""The ablation vocabulary is a contract, not a convenience.

An ablation that silently no-ops is a broken instrument: it will report "no effect" forever regardless
of the truth, and we would not notice. Every name here must resolve to a flag that exists and must
actually change it.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.copilot.flags import Flags  # noqa: E402
from src.eval import ablations  # noqa: E402


class TestAblationVocabulary(unittest.TestCase):
    def test_every_ablation_names_real_flags(self) -> None:
        fields = set(vars(Flags()))
        for name, spec in ablations.ABLATIONS.items():
            for field in spec:
                self.assertIn(field, fields, f"{name} sets unknown flag {field!r}")

    def test_every_ablation_actually_changes_something(self) -> None:
        """A default-valued ablation cannot move a score, so it is a broken instrument, not a null."""
        base = Flags()
        for name in ablations.ABLATIONS:
            with self.subTest(name=name):
                got = ablations.flags(name)
                self.assertNotEqual(
                    vars(got), vars(base),
                    f"{name!r} leaves every flag at its default — it can never move a score")

    def test_unknown_ablation_raises(self) -> None:
        with self.assertRaises(AssertionError):
            ablations.flags("no_such_ablation")

    def test_no_spec_phrase_removes_partial_credit_too(self) -> None:
        """The insurance number: it must remove BOTH the exact card string AND its normalised pair.

        Disabling only the exact matcher leaves the normalised `(attribute, value)` matcher reading
        the same inverted spec strings, which once overstated one road by ~0.09.
        """
        flags = ablations.flags("no_spec_phrase")
        self.assertFalse(flags.exact)
        self.assertFalse(flags.attribute)
        self.assertTrue(flags.lexical, "generic token overlap is retrieval, not inversion — it stays")


if __name__ == "__main__":
    unittest.main()
