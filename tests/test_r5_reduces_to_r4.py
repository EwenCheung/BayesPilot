"""R5-A1 — R5 with its new mechanisms off IS R4.

Same contract as R4-A1: the road's claim is that it differs from its parent in a small, named set of
places, and a subclass that silently changes behaviour makes every downstream delta uninterpretable.
"""
from __future__ import annotations

import contextlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import harness, race  # noqa: E402


@contextlib.contextmanager
def offline():
    previous = os.environ.get("R3_OFFLINE")
    os.environ["R3_OFFLINE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("R3_OFFLINE", None)
        else:
            os.environ["R3_OFFLINE"] = previous


def _rows(road: str) -> dict[str, tuple]:
    with offline():
        result = harness.run(race.ROADS[road]())
    return {s["sample_id"]: (s["hit"], s["first_hit_turn"], s["best_rank"]) for s in result["sessions"]}


class TestR5ReducesToR4(unittest.TestCase):
    def test_every_new_mechanism_defaults_off(self) -> None:
        from src.r5.flags import Flags
        flags = Flags()
        self.assertFalse(flags.freetext_category, "measured to buy nothing (D16); default off")
        self.assertFalse(flags.freetext_route, "measured slightly negative (D16); default off")
        self.assertFalse(flags.llm_fallback)

    def test_r5_inherits_r4s_fitted_constants(self) -> None:
        from src.r4.flags import Flags as R4Flags
        from src.r5.flags import Flags as R5Flags
        r4, r5 = R4Flags(), R5Flags()
        for name in ("prior_weight", "v_continue", "tau_mass", "soft_card_gain", "exclude_shipped"):
            self.assertEqual(getattr(r5, name), getattr(r4, name), name)

    def test_r5_reproduces_r4_session_for_session(self) -> None:
        r4, r5 = _rows("r4"), _rows("r5")
        self.assertEqual(set(r4), set(r5))
        differing = {k: (r4[k], r5[k]) for k in r4 if r4[k] != r5[k]}
        self.assertEqual(differing, {}, f"{len(differing)} sessions differ; src/r5/ has drifted")


if __name__ == "__main__":
    unittest.main()
