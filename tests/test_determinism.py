"""Identical inputs must give identical scores across processes.

Python salts string hashing per interpreter, so any place that iterates a `set` and truncates picks a
different subset each run. This has bitten this codebase before — the score drifted 0.9584 / 0.9594
from exactly that, and the fix made the model *correct*, not merely stable. A score that moves
between identical runs cannot be compared to anything.

Run in fresh interpreters with hash randomisation left ON, so the bug can actually appear.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROBE = (
    "import sys; sys.path.insert(0, {root!r});"
    "from src.eval import measure;"
    "print('%.10f' % measure.score())"
)


class TestDeterminism(unittest.TestCase):
    def _score_in_fresh_process(self, seed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": seed, "COPILOT_OFFLINE": "1"}
        out = subprocess.run([sys.executable, "-c", PROBE.format(root=str(ROOT))],
                             capture_output=True, text=True, cwd=ROOT, env=env, timeout=600)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        return out.stdout.strip()

    def test_score_is_identical_under_different_hash_seeds(self) -> None:
        a = self._score_in_fresh_process("1")
        b = self._score_in_fresh_process("2")
        self.assertEqual(a, b, f"score drifted between hash seeds: {a} vs {b}")


if __name__ == "__main__":
    unittest.main()
