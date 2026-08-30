"""R4-A1 — the kill gate. R4 with every new flag off IS R3.

`src/r4/agent.py` copies R3's `_respond` rather than calling it (see that file's docstring for why).
A copy drifts. This test is the thing that makes the copy safe: it compares **per-session rank and
turn**, not aggregate score, because two different agents can reach the same TechnicalScore by
different routes and an aggregate check would pass while the systems diverged.

🔴 If this fails, stop. Every R4 measurement downstream is a comparison against an unknown baseline.
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
    """⚠️ Scoped, not module-level. Setting `R3_OFFLINE` at import time leaks into every module the
    runner imports afterwards — it silently broke three `tests/test_llm.py` cases, which pass alone
    and fail in the suite. Environment set at import scope is a test that edits other tests."""
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
    """⚠️ R4's inherited constants were re-fitted on train.jsonl (D14), so a default R4 is no longer
    numerically R3. This test is about the **code path**, not the constants: R4's `_respond` is a copy
    of R3's and the copy must not drift. So R4 is constructed and its six inherited constants are
    reset to R3's before comparing."""
    with offline():
        agent = race.ROADS[road]()
        if road == "r4":
            from src.r3.flags import Flags as R3Flags
            r3 = R3Flags()
            for name in ("prior_weight", "v_continue", "tau_mass",
                         "stall_decay", "stall_decay_clean", "exact_gain"):
                setattr(agent.flags, name, getattr(r3, name))
            # `soft_card_gain` is a fitted constant too (D15), not a mechanism switch — R3 has no
            # equivalent field, so it is reset to its off value rather than to an R3 default.
            agent.flags.soft_card_gain = 0.0
        result = harness.run(agent)
    return {s["sample_id"]: (s["hit"], s["first_hit_turn"], s["best_rank"]) for s in result["sessions"]}


class TestR4ReducesToR3(unittest.TestCase):
    def test_default_flags_are_all_off(self) -> None:
        """R4-A1: every new MECHANISM defaults off, so the reduction below isolates the code path."""
        from src.r4.flags import Flags
        flags = Flags()
        self.assertFalse(flags.exclude_shipped)
        self.assertEqual(flags.truncate, 0, "truncation is measured-negative (D4); default off")
        self.assertEqual(flags.soft_card_gain, 1.5, "fitted on train (D15); 2.5 regressed clean")

    def test_r4_reproduces_r3_session_for_session(self) -> None:
        """R4-A1: identical rank AND turn on every session, not merely an identical score."""
        r3, r4 = _rows("r3"), _rows("r4")
        self.assertEqual(set(r3), set(r4))
        differing = {k: (r3[k], r4[k]) for k in r3 if r3[k] != r4[k]}
        self.assertEqual(differing, {},
                         f"{len(differing)} sessions differ; src/r4/agent.py has drifted from R3")


if __name__ == "__main__":
    unittest.main()
