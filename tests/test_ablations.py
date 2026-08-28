"""M7 — one ablation vocabulary, meaning the same removal in every road.

Before this, `no_spec_phrase` = 0.9260 (R1) and 0.8315 (R2) were quoted side by side as if comparable.
They were not: R1's switch disabled only the exact matcher, while its normalised `(attribute, value)`
matcher went on reading the SAME inverted spec strings and recovered most of the signal — partial
credit for the inversion, which R2's flag removes. R1 defect 1 puts the overstatement at ~0.09.

The shared definition: `no_spec_phrase` removes all credit derived from the simulator's inverted spec
strings, exact AND partial. Generic lexical/token overlap survives in both roads, because that is a
retrieval signal rather than an inversion signal.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import ablations, race  # noqa: E402


class TestM7SharedVocabulary(unittest.TestCase):
    def test_every_road_accepts_every_shared_ablation(self) -> None:
        """M7: an ablation name is meaningless if a road silently ignores it."""
        for name in ablations.SHARED:
            for road in race.ROADS:
                self.assertIn(road, ablations.SHARED[name],
                              f"road {road} has no translation for {name}")

    def test_no_spec_phrase_removes_partial_credit_in_r1(self) -> None:
        """M7: R1's flag must disable the normalised-pair matcher too, not just the exact one."""
        flags = ablations.r1_flags("no_spec_phrase")
        self.assertFalse(flags.spec_phrase, "exact matcher still live")
        self.assertFalse(flags.attribute, "partial credit still live - this is R1 defect 1")
        self.assertTrue(flags.token, "generic lexical overlap is retrieval, not inversion")

    def test_no_spec_phrase_is_now_strictly_harsher_for_r1(self) -> None:
        """M7: the corrected ablation must score BELOW R1's published 0.9260.

        If it does not, the flag is still leaking inversion signal and the number is still overstated.
        """
        corrected = race.score_road("r1", ablate="no_spec_phrase")
        self.assertLess(corrected, 0.9260,
                        f"corrected no_spec_phrase {corrected:.4f} did not drop below the "
                        f"published 0.9260 - the leak is still open")


if __name__ == "__main__":
    unittest.main()
